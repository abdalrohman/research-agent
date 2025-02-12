# app.py
import asyncio
import os

import streamlit as st  # type: ignore

from correlation import get_correlation_id
from research_agent import SearchAgent
from constant import STORE_FOLDER

def run_research_agent(question: str, depth: int) -> str:
    # Create a new instance of the agent; this sets a new correlation ID for this session.
    agent = SearchAgent()
    # Execute the research pipeline and return the final report.
    final_report = asyncio.run(agent.execute(question, depth))
    return final_report


st.title("Research Agent")
st.write(
    "Enter your research question and select the desired research depth. Once the processing is complete, you can download your report."
)

question = st.text_input(
    "Research Question", placeholder="e.g., Which treatment option is better for managing ischemic stroke?"
)
depth = st.number_input("Research Depth (number of follow-up rounds)", min_value=1, max_value=5, value=2, step=1)

if st.button("Submit"):
    if not question.strip():
        st.error("Please provide a valid research question.")
    else:
        with st.spinner("Processing your research query... This may take a few moments."):
            try:
                final_report = run_research_agent(question, depth)
                st.success("Final report generated!")
                st.markdown(final_report)

                # Retrieve the correlation ID for this session.
                # This agent use the correlation ID to diffrentiate reports for each user.
                cid = get_correlation_id()
                # Construct the expected path to the report file.
                report_file_path = os.path.join(STORE_FOLDER, f"{cid}.md")

                if os.path.exists(report_file_path):
                    with open(report_file_path, "rb") as file:
                        file_bytes = file.read()
                        st.download_button(
                            label="Download Report", data=file_bytes, file_name=f"report_{cid}.md", mime="text/markdown"
                        )
                else:
                    st.warning("The report file could not be located. Please check the logs.")

            except Exception as e:
                st.error(f"An error occurred during processing: {e}")

st.write(
    "Your final research report will be displayed above once processing is complete, along with a download button for your convenience."
)
