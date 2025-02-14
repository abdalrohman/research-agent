document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("researchForm");
  const questionInput = document.getElementById("question");
  const depthSlider = document.getElementById("depth");
  const depthValue = document.getElementById("depthValue");
  const resultsContainer = document.getElementById("resultsContainer");
  const reportContent = document.getElementById("reportContent");
  const downloadReport = document.getElementById("downloadReport");
  const loadingOverlay = document.getElementById("loadingOverlay");
  const submitButton = form.querySelector('button[type="submit"]');

  // Update the depth display in real-time
  depthSlider.addEventListener("input", () => {
    depthValue.textContent = depthSlider.value;
  });

  // Prevent multiple download event bindings
  let downloadBound = false;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    // Disable the submit button to prevent duplicate submissions
    submitButton.disabled = true;
    submitButton.classList.add("opacity-50", "cursor-not-allowed");

    const question = questionInput.value.trim();
    if (!question) {
      alert("Please enter a research question");
      submitButton.disabled = false;
      submitButton.classList.remove("opacity-50", "cursor-not-allowed");
      return;
    }

    // Show loading overlay and mark as busy for accessibility
    loadingOverlay.classList.remove("hidden");
    loadingOverlay.setAttribute("aria-busy", "true");
    resultsContainer.classList.add("hidden");

    try {
      const response = await fetch("/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question,
          depth: parseInt(depthSlider.value),
        }),
      });

      if (!response.ok) {
        throw new Error(`Research failed (Status: ${response.status})`);
      }

      const data = await response.json();
      displayResults(data.report);

      // Optionally, clear the form after successful submission
      form.reset();
      depthValue.textContent = depthSlider.value;
    } catch (error) {
      console.error("Error:", error);
      alert("Research failed: " + error.message);
    } finally {
      // Hide loading overlay and re-enable the submit button
      loadingOverlay.classList.add("hidden");
      loadingOverlay.removeAttribute("aria-busy");
      submitButton.disabled = false;
      submitButton.classList.remove("opacity-50", "cursor-not-allowed");
    }
  });

  function displayResults(report) {
    if (!report) {
      alert("No results available");
      return;
    }
    try {
      // Convert markdown to HTML using marked
      const htmlContent = marked.parse(report);
      reportContent.innerHTML = htmlContent;
      resultsContainer.classList.remove("hidden");
      resultsContainer.scrollIntoView({ behavior: "smooth" });

      if (!downloadBound) {
        downloadReport.addEventListener("click", () =>
          downloadMarkdownFile(report)
        );
        downloadBound = true;
      }
    } catch (error) {
      console.error("Error parsing markdown:", error);
      alert("Error displaying results: " + error.message);
    }
  }

  function downloadMarkdownFile(content) {
    const blob = new Blob([content], { type: "text/markdown" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "research-report.md";
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  }
});
