import asyncio
import json
import uuid
from datetime import UTC, datetime

import aiofiles  # type: ignore
import litellm
from crawl4ai import (  # type: ignore
    AsyncWebCrawler,
    BM25ContentFilter,
    BrowserConfig,
    CacheMode,
    CrawlerMonitor,
    CrawlerRunConfig,
    CrawlResult,
    DisplayMode,
    MemoryAdaptiveDispatcher,
    RateLimiter,
)  # type: ignore
from crawl4ai.chunking_strategy import SlidingWindowChunking  # type: ignore
from crawl4ai.content_filter_strategy import PruningContentFilter  # type: ignore
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator  # type: ignore
from dotenv import find_dotenv, load_dotenv

from constant import (
    ANSWER_TEMPERATURE,
    COOL_DOWN_DELAY,
    MAX_CONCURRENT_SEARCHES,
    MAX_NUM_OF_QUERIES,
    MAX_RESEARCH_GOALS,
    MAX_RETRIES,
    MAX_SEARCH_RESULTS,
    NUM_FOLLOWUP_QUESTIONS,
    NUM_INSIGHTS,
    QUERY_TEMPERATURE,
    RESEARCH_DEPTH,
    SAFE_MAX_INPUT_TOKEN,
    STORE_FOLDER,
    THINKING_MODEL,
)
from correlation import get_correlation_id, set_correlation_id
from decorator import add_file_logging, log, retry, trace_decorator  # type: ignore
from llm import call_llm
from models import Chunk, SearchContext, SearchResult
from search import search_searxng
from utils import estimate_tokens, remove_extra_line_breaks

# Load enviromental variables
_ = load_dotenv(find_dotenv())


async def cool_down(duration: int = COOL_DOWN_DELAY) -> None:
    log.info(f"Waiting {duration}s for cool down...")
    await asyncio.sleep(duration)


class QueryGenerator:
    """Generates optimized search queries based on context and previous results"""

    @staticmethod
    @trace_decorator
    @retry(
        max_retries=MAX_RETRIES,
        delay=3,
        backoff=2,
        exceptions=(litellm.exceptions.RateLimitError),
    )
    async def execute(
        question: str,
        context: SearchContext,
        max_queries: int = MAX_NUM_OF_QUERIES,
        num_research_goals: int = MAX_RESEARCH_GOALS,
    ) -> None:
        insights = f"{context.insights if context.insights else ''}"
        pending_goals = "\n".join([rg for rg in context.research_goals if rg not in context.processed_goals])

        prompt = remove_extra_line_breaks(f"""<role>
You are an expert Information Retrieval Specialist, highly skilled in creating effective search queries for complex research topics across diverse domains (academic, technical, medical, general).
</role>

<task>
Your primary goal is to generate exactly {max_queries} search queries that are highly relevant, diverse, and optimized for retrieving authoritative and recent information to answer the research question: "{question}". Strive for a balance between broad coverage (recall) and focused relevance (precision).
</task>

<context>
<datetime>{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}</datetime>
{ 'Previous Research Insights: ' + insights if insights else 'No previous insights.' }
{ 'Pending Research Goals: ' + pending_goals if pending_goals else 'No pending research goals.' }
</context>

<query_guidelines>
1. **Query Characteristics:**
    * **Relevance:** Each query must directly relate to the research question.
    * **Diversity:** Queries should explore different facets, keywords, and perspectives of the question. Avoid generating very similar queries.
    * **Authority:** Prioritize queries designed to retrieve results from authoritative sources (e.g., academic institutions, government agencies, reputable organizations).
    * **Recency:** Where applicable, include temporal filters to prioritize recent information (e.g., last 2-3 years for current events or rapidly evolving fields, consider temporal relevance for other domains).

2. **Search Operators & Domain Adaptation:**
    * Utilize advanced search operators to refine queries (e.g., quotes for exact phrases, OR/-, `site:`, `intitle:`, `intext:`, `after:`). Refer to the "Reference Search Operators" list if needed.
    * Adapt query construction based on the likely domain of the research question. Consider applying domain-specific filters (examples below):
        * **Academic/Research:** `site:(gov OR edu OR org)`, `intitle:"research" OR intitle:"study"`
        * **Medical/Clinical:** `"peer-reviewed"`, `intext:"clinical trial" OR intext:"evidence-based" OR intext:"guidelines"`
        * **Technical/Code-related:** `intext:"code" OR intext:"algorithm"`, `filetype:(pdf OR doc OR txt)` (use filetype cautiously as per original instructions)
        * **Current Events:** `after:{datetime.now(UTC).strftime('%Y-%m')}`

3. **Query Structure (Progressive Layers):** Consider constructing queries to address different layers of understanding:
    * **Core Concepts:** Define fundamental terms and concepts.
    * **Current State:** Explore recent developments, trends, and the current understanding of the topic.
    * **Evidence & Validation:** Seek evidence, data, and validation for claims or theories.
    * **Applications & Implications:** Investigate practical applications, real-world impact, and broader implications.

4. **Constraints:**
    * Each query should ideally be under 80 characters for optimal search engine compatibility.
    * Aim to include at least one or two effective search operators in each query to enhance precision.

5. **Research Goals Generation:** In addition to queries, propose {num_research_goals} unique and actionable research goals. Each goal should:
    * Clearly state a specific direction for further research.
    * Explain how pursuing this goal will advance the understanding of the main research question.
    * Be distinct from previously generated research goals.

</query_guidelines>

<output_format>
Your output must be a valid JSON object with the following structure:
{{
  "queries": ["query1", "query2", ...],
  "research_goals": ["research goal 1", "research goal 2", ...]
}}
Ensure the JSON is valid and contains ONLY the JSON object, with no extra text or formatting.
</output_format>
""")

        log.debug(f"[QueryGenerator] Prompt: {prompt[:200]}...")
        queries, token_count = await call_llm(
            messages=[{"role": "user", "content": prompt}],
            response_schema={
                "type": "object",
                "properties": {
                    "queries": {"type": "array", "items": {"type": "string"}},
                    "research_goals": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["queries", "research_goals"],
            },
            temperature=QUERY_TEMPERATURE,
            context=context,
        )

        result: dict[str, list[str]] = json.loads(queries)
        log.info(
            f"[QueryGenerator] Generated {len(result['queries'])} queries and {len(result['research_goals'])} research goals (Token Usage: {token_count})"
        )
        log.info(f"[QueryGenerator] Generated queries: {result['queries']}")
        context.search_queries.update(set(result["queries"]))
        new_goals = set(result["research_goals"])
        context.research_goals.update(new_goals)
        await cool_down()


class WebSearch:
    def __init__(self, max_concurrent_searches: int = MAX_CONCURRENT_SEARCHES):
        self.semaphore = asyncio.Semaphore(max_concurrent_searches)

    @trace_decorator
    @retry(
        max_retries=MAX_RETRIES,
        delay=3,
        backoff=2,
    )
    async def execute(
        self,
        context: SearchContext,
        max_searches: int = MAX_SEARCH_RESULTS,
    ) -> None:
        queries = [q for q in context.search_queries if q not in context.processed_queries]
        log.info(f"[WebSearch] Processing {len(queries)} new search queries")

        async def execute_query(query) -> list[SearchResult]:
            async with self.semaphore:
                try:
                    results = await search_searxng(query=query, count=max_searches)
                    context.processed_queries.add(query)
                except Exception as e:
                    log.error(f"[WebSearch] Error processing query '{query}': {e}")
                    return []
                return results

        results = await asyncio.gather(*[execute_query(q) for q in queries])
        total_urls = 0
        seen_urls = set(context.processed_urls) | {result.url for result in context.search_results}
        for sublist in results:
            if sublist:
                valid_results = [
                    result for result in sublist if self._is_valid_url(result.url) and result.url not in seen_urls
                ]
                total_urls += len(valid_results)
                for result in valid_results:
                    context.search_results.append(result)
                    seen_urls.add(result.url)
        log.info(f"[WebSearch] Processed {len(queries)} queries and obtained {total_urls} valid URLs")

    def _is_valid_url(self, url: str) -> bool:
        invalid_exts = {"pdf", "doc", "ppt"}
        invalid_domains = {
            "facebook.com",
            "twitter.com",
            "x.com",
            "linkedin.com",
            "instagram.com",
            "pinterest.com",
            "tiktok.com",
            "snapchat.com",
            "reddit.com",
            "uptodate.com",
            "medscape.com",
            "bmj.com",
        }  # filter all domains needing login or any social media accounts or any paid sites
        return not any(ext in url.lower() for ext in invalid_exts) and not any(
            domain in url.lower() for domain in invalid_domains
        )


class ContentExtractor:
    def __init__(self):
        self.browser_config = BrowserConfig(headless=True, verbose=False)
        self.dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=90.0,
            check_interval=1.0,
            max_session_permit=10,
            rate_limiter=RateLimiter(base_delay=(1.0, 2.0), max_delay=30.0, max_retries=2),
            monitor=CrawlerMonitor(max_visible_rows=15, display_mode=DisplayMode.DETAILED),
        )
        self.run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            verbose=False,
            exclude_social_media_links=True,
            exclude_external_links=True,
            exclude_external_images=True,
            simulate_user=True,
            remove_overlay_elements=True,
            check_robots_txt=True,
            scan_full_page=False,
            chunking_strategy=SlidingWindowChunking(),
            content_filter=PruningContentFilter(),
            markdown_generator=DefaultMarkdownGenerator(
                options={
                    "ignore_links": True,
                    "ignore_images": True,
                    "escape_snob": True,
                }
            ),
        )

    @trace_decorator
    # @retry(max_retries=2, delay=3, backoff=2) # Do'nt retry error is common in one url but not in all
    async def execute(self, question: str, context: SearchContext) -> None:
        urls = [result.url for result in context.search_results if result.url not in context.processed_urls]
        log.info(f"[ContentExtractor] Extracting content from {len(urls)} new URLs")
        self.run_config.content_filter = BM25ContentFilter(user_query=question)
        async with AsyncWebCrawler(config=self.browser_config) as crawler:
            results: list[CrawlResult] = await crawler.arun_many(
                urls=urls, config=self.run_config, dispatcher=self.dispatcher
            )  # type: ignore

        extracted_chunks = 0
        for result in results:
            if not result.success:
                log.error(f"[ContentExtractor] Failed to crawl {result.url}")
                continue
            chunk = Chunk(
                url=result.url,
                content=result.markdown_v2.markdown_with_citations,  # type: ignore
                tokens=estimate_tokens(result.markdown_v2.markdown_with_citations),  # type: ignore
                metadata=result.metadata if result.metadata else {},
                references=result.markdown_v2.references_markdown,  # type: ignore
            )
            context.chunks.append(chunk)
            context.processed_urls.add(result.url)  # ensure we don't process the same URL twice
            extracted_chunks += 1
        log.info(f"[ContentExtractor] Extracted {extracted_chunks} content chunks")


class GenerateInsights:
    @trace_decorator
    @retry(
        max_retries=MAX_RETRIES,
        delay=15,
        backoff=2,
        exceptions=(litellm.exceptions.RateLimitError,),
    )
    async def execute(
        self,
        question: str,
        context: SearchContext,
        num_insights: int = NUM_INSIGHTS,
        num_followup_questions: int = NUM_FOLLOWUP_QUESTIONS,
    ) -> None:
        # TODO: Think about to generate followup question in seperate session
        # insights_str = "\n".join(context.insights)
        # followups_str = "\n".join(context.followup_questions)
        insights_summary = (
            f"({len(context.insights)} previous insights summarized): "
            + f"'{', '.join(context.insights[-3:] if len(context.insights) > 3 else context.insights)}' (showing last 3)'"
            if context.insights
            else "None"
        )
        followup_summary = (
            f"({len(context.followup_questions)} previous questions summarized): "
            + f"'{', '.join(context.followup_questions[-3:] if len(context.followup_questions) > 3 else context.followup_questions)}' (showing last 3)'"
            if context.followup_questions
            else "None"
        )
        pending_goals = "\n".join([rg for rg in context.research_goals if rg not in context.processed_goals])

        log.info(f"[GenerateInsights] Processing {len(context.chunks) - len(context.processed_chunks)} new chunks")
        accumulated_followups = []
        for chunk in context.chunks:
            if chunk.chunk_id in context.processed_chunks:
                continue
            content = chunk.content
            if chunk.tokens > SAFE_MAX_INPUT_TOKEN:
                log.warning(
                    f"[GenerateInsights] Content too large from {chunk.url} ({chunk.tokens} tokens); truncating to {SAFE_MAX_INPUT_TOKEN} tokens"
                )
                content = SlidingWindowChunking(window_size=int(SAFE_MAX_INPUT_TOKEN)).chunk(chunk.content)[0]

            prompt = f"""<role>
You are a Research Analyst tasked with analyzing search results content to extract key insights and formulate valuable follow-up questions.
</role>

<task>
Analyze the provided web content and perform the following:
1. **Identify and Extract Key Insights:**  From the content, extract up to {num_insights} key insights that are highly relevant to the overarching research question: "{question}". These insights should be concise, information-rich, and unique, guiding further research and highlighting important discoveries or perspectives.
2. **Formulate Follow-up Questions:** Generate up to {num_followup_questions} insightful follow-up questions that logically extend the current investigation and probe deeper into unanswered aspects or newly identified areas of interest. These questions should be derived from the content and insights, aiming to deepen the understanding of the research question.
</task>

To ensure high-quality insights and questions, consider the following:

<analysis_guidelines>
1. **Content Focus:** Prioritize information directly relevant to the research question. Identify key facts, trends, unique arguments, and data points presented in the content.

2. **Insight Quality:** Each insight should be:
    * **Concise:** Expressed briefly and clearly.
    * **Information-Dense:** Packed with specific and actionable information.
    * **Unique and Novel:**  Offer a distinct observation, not a repetition of previous insights.
    * **Grounded in Content:** Directly supported by evidence from the provided web content. Ideally, mention the source URL for traceability (if possible within JSON output constraints).

3. **Follow-up Question Quality:** Each follow-up question should be:
    * **Relevant:** Directly related to the research question and the insights derived from the content.
    * **Insightful:**  Probe deeper, seeking to uncover new information or resolve ambiguities.
    * **Specific and Actionable:** Guide future research effectively, leading to concrete next steps.

4. **Contextual Awareness (Summarized):** To maintain focus and efficiency, previous research context is summarized below:
    * **Pending Research Goals:** {pending_goals if pending_goals else 'None'}
    * **Summary of Previous Insights:** {insights_summary}
    * **Summary of Previous Follow-up Questions:** {followup_summary}
    * **Note:** While detailed previous context is summarized above, prioritize new insights and questions derived primarily from the *current* content to maintain focus and avoid excessive repetition.

</analysis_guidelines>

<content_to_analyze>
<question>{question}</question>
<datetime>{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}</datetime>
<content>{content}</content>
</content_to_analyze>


<output_format>
Your output must be a valid JSON object with the following structure:
{{
  "insights": ["insight 1", "insight 2", ...],
  "followup_questions": ["follow-up question 1", "follow-up question 2", ...]
}}
Ensure the JSON is valid and contains ONLY the JSON object, with no extra text or formatting.
</output_format>
"""
            prompt = remove_extra_line_breaks(prompt)
            log.debug(f"[GenerateInsights] Prompt before LLM call: {prompt[:200]}...")
            response, token_count = await call_llm(
                messages=[{"role": "user", "content": prompt}],
                response_schema={
                    "type": "object",
                    "properties": {
                        "insights": {"type": "array", "items": {"type": "string"}},
                        "followup_questions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["insights", "followup_questions"],
                },
                temperature=QUERY_TEMPERATURE,
                context=context,
            )
            context.processed_chunks.add(chunk.chunk_id)
            result: dict[str, list[str]] = json.loads(response)
            log.info(
                f"[GenerateInsights] Obtained {len(result['insights'])} insights, {len(result['followup_questions'])} follow-up questions (Token Usage: {token_count})"
            )
            if result["insights"]:
                context.insights.extend(result["insights"])
            if result["followup_questions"]:
                accumulated_followups.extend(result["followup_questions"])
            log.info(f"[GenerateInsights] Insights: {result['insights']}")
            log.info(f"[GenerateInsights] Follow-up Questions: {result['followup_questions']}")

            await cool_down()

        if accumulated_followups:
            unique_followups = list(dict.fromkeys(accumulated_followups))
            limited_followups = unique_followups[:num_followup_questions]
            context.followup_questions = limited_followups

        new_goals = set(context.research_goals)
        context.processed_goals.update(new_goals)
        context.research_goals = context.research_goals.difference(new_goals)


class FinalReport:
    @trace_decorator
    @retry(
        max_retries=MAX_RETRIES,
        delay=15,
        backoff=2,
        exceptions=(litellm.exceptions.RateLimitError,),
    )
    async def execute(self, context: SearchContext) -> str:
        unique_insights = list(dict.fromkeys(context.insights))
        unique_goals = list(dict.fromkeys(context.processed_goals))
        unique_followups = list(dict.fromkeys(context.processed_followup_questions))
        visited_urls = list(dict.fromkeys(context.processed_urls))

        insights_str = "\n".join(unique_insights)
        research_goals_str = "\n".join(unique_goals)
        followup_questions_str = "\n".join(unique_followups)
        visited_urls_str = "\n".join(visited_urls)

        log.info(
            f"[FinalReport] Final statistics: {len(unique_insights)} insights, {len(unique_goals)} goals, {len(unique_followups)} follow-up questions, {len(visited_urls)} visited URLs"
        )
        prompt = f"""<role>
You are a Senior Research Report Writer, expert in synthesizing research findings into comprehensive, structured, and insightful reports.
</role>

<task>
Using the provided research inputs (insights, research goals, follow-up questions, and visited URLs), write a detailed and comprehensive final research report on the topic: "{context.question}".  The report should be structured in Markdown format for optimal readability and aim for depth and clarity, not a specific page length.
</task>

Your report MUST include the following sections, in this order, and address the points outlined for each:

<report_structure>
1. **Executive Summary:** (Concise - approx. 1 paragraph)
    * Briefly summarize the research topic, key objectives, and most significant findings.

2. **Introduction:** (Approx. 2-3 paragraphs)
    * Provide a clear overview of the research topic and its background.
    * Explain the importance and relevance of the research question.
    * Briefly state the research goals that guided the investigation.

3. **Methodology:** (Approx. 1-2 paragraphs)
    * Briefly describe the research approach taken.
    * Outline the key steps of the research process (e.g., search query generation, web content extraction, insight analysis).
    * Mention the types of sources consulted (e.g., academic websites, news articles, etc. - based on visited URLs).

4. **Key Findings:** (Detailed and thematically organized - multiple paragraphs/subsections as needed)
    * Present the most important findings and insights derived from the research.
    * Organize findings thematically for clarity. Use subheadings for each theme.
    * For each finding, provide sufficient detail and context.  Reference the insights from which these findings are synthesized (though not as formal citations, just for internal traceability during generation).

5. **In-depth Analysis and Discussion:** (Analytical and interpretive - several paragraphs)
    * Analyze the key findings in detail. Discuss their implications, significance, and potential impact.
    * Explore trends, patterns, and any anomalies or contradictions identified during the research.
    * Discuss different perspectives or viewpoints encountered in the sources.
    * Critically evaluate the findings. Acknowledge any limitations of the research or potential biases in the sources (if evident).

6. **Conclusion:** (Concise - approx. 1-2 paragraphs)
    * Summarize the overall conclusions of the research, directly answering the initial research question as comprehensively as possible based on the findings.
    * Reiterate the most significant insights in a concluding manner.

7. **Recommendations for Future Research (Optional):** (If applicable and relevant - approx. 1 paragraph)
    * Based on the research outcomes and any remaining unanswered questions, suggest specific directions for future research or further investigation.

8. **Sources:** (List - bulleted list of URLs)
    * Provide a bulleted list of all visited URLs and sources used in the research.

</report_structure>

<research_inputs>
<insights>{insights_str}</insights>
<research_goals>{research_goals_str}</research_goals>
<followup_questions>{followup_questions_str}</followup_questions>
<visited_urls>{visited_urls_str}</visited_urls>
</research_inputs>

<formatting_requirements>
* **Markdown Format:** The entire report MUST be in valid Markdown format.
* **Clear Headings:** Use Markdown headings (e.g., ## Section Title, ### Subheading) for all sections and subsections as indicated in the <report_structure>.
* **Bulleted Lists:** Use Markdown bulleted lists for the Sources section and where appropriate within other sections (e.g., for listing key findings).
* **Emphasis:** Use Markdown bold and italics for emphasis where needed.
</formatting_requirements>

Ensure the final output is a complete and well-formatted Markdown report and nothing else.
"""

        prompt = remove_extra_line_breaks(prompt)
        log.debug(f"[FinalReport] Final report prompt (first 200 chars): {prompt[:200]}...")
        final_report, token_count = await call_llm(
            model=THINKING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=ANSWER_TEMPERATURE,
            context=context,
        )
        final_report = self.sanitize_report(final_report)
        log.info(f"[FinalReport] Final Report generated successfully (Token Usage: {token_count})")
        await self.write_report(final_report)
        return final_report

    async def write_report(self, report: str) -> None:
        log.info(f"[FinalReport] Writing report to {get_correlation_id()}.md")
        async with aiofiles.open(f"{STORE_FOLDER}/{get_correlation_id()}.md", "w") as f:
            await f.write(report)

    def sanitize_report(self, report: str) -> str:
        # Remove starting "```markdown" (case-sensitive) if present
        if report.startswith("```markdown"):
            report = report[len("```markdown") :].lstrip("\n")
        # Remove ending "```" if present
        if report.endswith("```"):
            report = report[:-3].rstrip("\n")
        return report


class SearchAgent:
    def __init__(self) -> None:
        self._current_cid = None
        self._init_correlation_id()
        add_file_logging(self._current_cid if self._current_cid else "")
        self.search = WebSearch()
        self.query_generator = QueryGenerator()
        self.insights = GenerateInsights()
        self.content_extractor = ContentExtractor()
        self.final_report = FinalReport()

    def _init_correlation_id(self):
        if not self._current_cid:
            self._current_cid = uuid.uuid4().hex[:12]
            set_correlation_id(self._current_cid)
        return self._current_cid

    @trace_decorator
    async def execute(self, question: str, depth: int = RESEARCH_DEPTH) -> str:
        context = SearchContext(question=question)

        # Execute main search pipeline
        await self.query_generator.execute(context.question, context)
        await self.search.execute(context)
        await self.content_extractor.execute(context.question, context)
        await self.insights.execute(context.question, context)

        for round_number in range(1, depth + 1):
            pending_followups = list(context.followup_questions)
            if not pending_followups:
                log.info(f"[SearchAgent] No pending follow-up questions in round {round_number}. Ending iteration.")
                break

            context.followup_questions.clear()
            log.info(
                f"[SearchAgent] --- Starting depth round {round_number}/{depth} with {len(pending_followups)} follow-up question(s) ---"
            )
            for idx, followup in enumerate(pending_followups):
                log.info(
                    f"[SearchAgent] Round {round_number} - Processing follow-up {idx+1}/{len(pending_followups)}: {followup}"
                )
                await self.query_generator.execute(followup, context)
                await self.search.execute(context)
                await self.content_extractor.execute(followup, context)
                await self.insights.execute(followup, context)
                context.processed_followup_questions.add(followup)
            await cool_down()

        await cool_down(20)
        final_report = await self.final_report.execute(context)

        dashboard = (
            f"📊 ===== DASHBOARD SUMMARY ===== 📊\n"
            f"💰 Total Token Usage: {context.token_usage}\n"
            f"🔍 Total Search Queries Generated: {len(context.search_queries)}\n"
            f"✅ Total Processed Queries: {len(context.processed_queries)}\n"
            f"💡 Total Insights Extracted: {len(context.insights)}\n"
            f"❓ Total Follow-up Questions Processed: {len(context.processed_followup_questions)}\n"
            f"🎯 Total Research Goals Processed: {len(context.processed_goals)}\n"
            f"🌐 Total URLs Processed: {len(context.processed_urls)}\n"
            f"📝 Total Chunks Extracted: {len(context.chunks)}\n"
            f"📌 Total Processed Chunks (by ID): {len(context.processed_chunks)}\n"
            f"🔎 Generated Search Queries:\n"
            f"{chr(10).join(['   • ' + query for query in context.search_queries])}\n"
            f"🏆 Goals Processed:\n"
            f"{chr(10).join(['   📍 ' + goal for goal in context.processed_goals])}\n"
            f"✨ Sample Insights:\n"
            f"{chr(10).join(['   💫 ' + insight for insight in context.insights[:3]])}\n"
            f"🤔 Follow-up Questions Processed:\n"
            f"{chr(10).join(['   ❔ ' + q for q in context.processed_followup_questions])}\n"
            f"❗ Original Question: {context.question}\n"
            f"📊 ============================= 📊\n"
        )
        log.info(dashboard)

        return final_report


if __name__ == "__main__":
    import argparse

    from rich.console import Console
    from rich.markdown import Markdown

    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Research Agent - An AI-powered research assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python research_agent.py "What are the different types of brain tumors?" --depth 2
    python research_agent.py "Which treatment option is better for managing ischimic stroke?" --depth 3
    """,
    )

    # Add arguments
    parser.add_argument(
        "question",
        type=str,
        help="The research question to investigate",
    )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=2,
        help="Research depth level (default: 2)",
    )

    # Parse arguments
    args = parser.parse_args()

    # Initialize agent and console
    agent = SearchAgent()
    console = Console()

    # Execute search and display results
    console.print(f"\n🔍 Researching: {args.question}")
    console.print(f"📚 Research depth: {args.depth}\n")

    report = asyncio.run(agent.execute(args.question, args.depth))
    console.print(Markdown(report))
