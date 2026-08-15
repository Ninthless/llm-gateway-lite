const baseUrl = `${window.location.origin}/cursor`;
const baseUrlElement = document.querySelector("#base-url");
const healthDot = document.querySelector("#health-dot");
const healthLabel = document.querySelector("#health-label");
const refreshButton = document.querySelector("#refresh-health");
const toast = document.querySelector("#toast");
let toastTimer;

baseUrlElement.textContent = baseUrl;

function showToast(message) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("visible");
  toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 1800);
}

async function copyText(targetId) {
  const target = document.getElementById(targetId);
  await navigator.clipboard.writeText(target.textContent);
  showToast("已复制");
}

async function checkHealth() {
  refreshButton.disabled = true;
  healthDot.className = "health-dot";
  healthLabel.textContent = "正在检查网关";

  try {
    const response = await fetch("/health/readiness", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    healthDot.classList.add("ready");
    healthLabel.textContent = "网关运行正常";
  } catch {
    healthDot.classList.add("failed");
    healthLabel.textContent = "网关暂不可用";
  } finally {
    refreshButton.disabled = false;
  }
}

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await copyText(button.dataset.copyTarget);
    } catch {
      showToast("复制失败，请手动复制");
    }
  });
});

refreshButton.addEventListener("click", checkHealth);
checkHealth();
