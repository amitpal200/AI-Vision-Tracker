const toastElement = document.getElementById("appToast");
const toastText = document.getElementById("toastText");
const appToast = toastElement ? new bootstrap.Toast(toastElement) : null;

function notify(message) {
  if (!appToast) return;
  toastText.textContent = message;
  appToast.show();
}

document.getElementById("themeToggle")?.addEventListener("click", () => {
  const root = document.documentElement;
  root.dataset.bsTheme = root.dataset.bsTheme === "dark" ? "light" : "dark";
});

const liveImage = document.getElementById("liveImage");
const placeholder = document.getElementById("livePlaceholder");

document.getElementById("startLive")?.addEventListener("click", () => {
  liveImage.src = `${liveImage.dataset.src}?t=${Date.now()}`;
  liveImage.style.display = "block";
  placeholder.style.display = "none";
  notify("Live stream started");
});

document.getElementById("stopLive")?.addEventListener("click", async () => {
  await fetch("/api/camera/stop", { method: "POST" });
  liveImage.removeAttribute("src");
  liveImage.style.display = "none";
  placeholder.style.display = "grid";
  notify("Camera stopped");
});

document.getElementById("captureShot")?.addEventListener("click", async () => {
  const response = await fetch("/api/screenshot", { method: "POST" });
  const data = await response.json();
  notify(data.message || data.error);
});

const uploadForm = document.getElementById("uploadForm");
uploadForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(uploadForm);
  const response = await fetch("/api/upload", { method: "POST", body: formData });
  const data = await response.json();
  if (!response.ok) {
    notify(data.error || "Upload failed");
    return;
  }
  notify("Upload accepted");
  pollJob(data.job_id);
});

async function pollJob(jobId) {
  const progress = document.getElementById("uploadProgress");
  const status = document.getElementById("uploadStatus");
  const timer = setInterval(async () => {
    const response = await fetch(`/api/jobs/${jobId}`);
    const job = await response.json();
    progress.style.width = `${job.progress || 0}%`;
    progress.textContent = `${job.progress || 0}%`;
    status.textContent = `${job.status}: ${job.message || ""}`;
    if (job.status === "completed" || job.status === "failed") {
      clearInterval(timer);
      if (job.status === "completed" && job.output_file) {
        status.innerHTML = `Completed. <a href="/api/download/${job.output_file}">Download processed video</a>`;
      }
    }
  }, 1200);
}

async function loadHistory() {
  const table = document.getElementById("historyTable");
  if (!table) return;
  const response = await fetch("/api/history?limit=100");
  const rows = await response.json();
  if (!rows.length) {
    table.innerHTML = `<tr><td colspan="6" class="text-secondary">No detections have been logged yet.</td></tr>`;
    return;
  }
  table.innerHTML = rows.map((row) => `
    <tr>
      <td>${row.timestamp}</td>
      <td>${row.source_type}</td>
      <td>${row.file_name || ""}</td>
      <td>${row.class_name}</td>
      <td>${Number(row.confidence).toFixed(2)}</td>
      <td>${row.track_id}</td>
    </tr>
  `).join("");
}

async function loadJobs() {
  const table = document.getElementById("jobsTable");
  if (!table) return;
  const response = await fetch("/api/jobs?limit=50");
  const rows = await response.json();
  if (!rows.length) {
    table.innerHTML = `<tr><td colspan="6" class="text-secondary">No uploaded videos have been processed yet.</td></tr>`;
    return;
  }
  table.innerHTML = rows.map((job) => {
    const output = job.output_file && job.status === "completed"
      ? `<a href="/api/download/${job.output_file}">Download</a>`
      : `<span class="text-secondary">Not ready</span>`;
    return `
      <tr>
        <td>#${job.id}</td>
        <td>${job.source_file}</td>
        <td><span class="badge text-bg-${statusTone(job.status)}">${job.status}</span></td>
        <td>${job.progress || 0}%</td>
        <td>${Number(job.fps || 0).toFixed(2)}</td>
        <td>${output}</td>
      </tr>
    `;
  }).join("");
}

function statusTone(status) {
  if (status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "processing") return "info";
  return "secondary";
}

let classChart;
let systemChart;

async function loadDashboard() {
  if (!document.getElementById("classChart")) return;
  const response = await fetch("/api/analytics");
  const data = await response.json();
  document.getElementById("metricTotal").textContent = data.total_detected_objects || 0;
  document.getElementById("metricFps").textContent = data.fps || 0;
  document.getElementById("metricTime").textContent = `${data.processing_time_ms || 0} ms`;
  document.getElementById("metricAccuracy").textContent = `${data.overall_detection_accuracy || 0}%`;

  const labels = Object.keys(data.class_counts || {});
  const values = Object.values(data.class_counts || {});
  if (!classChart) {
    classChart = new Chart(document.getElementById("classChart"), {
      type: "bar",
      data: { labels, datasets: [{ label: "Objects by class", data: values, backgroundColor: "#31d2f2" }] },
      options: { responsive: true, maintainAspectRatio: false }
    });
    systemChart = new Chart(document.getElementById("systemChart"), {
      type: "doughnut",
      data: { labels: ["Active tracks", "FPS"], datasets: [{ data: [data.active_tracked_objects || 0, data.fps || 0], backgroundColor: ["#57cc99", "#ffd166"] }] },
      options: { responsive: true, maintainAspectRatio: false }
    });
  } else {
    classChart.data.labels = labels;
    classChart.data.datasets[0].data = values;
    classChart.update();
    systemChart.data.datasets[0].data = [data.active_tracked_objects || 0, data.fps || 0];
    systemChart.update();
  }
}

loadHistory();
loadJobs();
loadDashboard();
setInterval(loadJobs, 3000);
setInterval(loadDashboard, 2500);
