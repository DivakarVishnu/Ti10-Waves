// Mark a lesson complete via AJAX and update the progress bar without reloading
function markLessonComplete(contentId, btn) {
  fetch(`/student/content/${contentId}/complete`, { method: "POST" })
    .then((res) => res.json())
    .then((data) => {
      if (!data.success) return;
      const bar = document.getElementById("course-progress-bar");
      const label = document.getElementById("course-progress-label");
      if (bar) {
        bar.style.width = data.pct + "%";
        bar.setAttribute("aria-valuenow", data.pct);
      }
      if (label) {
        label.textContent = `${data.completed}/${data.total} lessons • ${data.pct}%`;
      }
      if (btn) {
        btn.innerHTML = '<i class="fa-solid fa-check"></i> Completed';
        btn.classList.remove("btn-accent");
        btn.classList.add("btn-outline-primary");
        btn.disabled = true;
      }
      const navItem = document.getElementById(`lesson-nav-${contentId}`);
      if (navItem) navItem.classList.add("completed");
    })
    .catch((err) => console.error("Failed to mark complete:", err));
}

// Mark a notification as read (fire-and-forget) when its card is clicked
function markNotificationRead(notifId, el) {
  fetch(`/student/notifications/${notifId}/read`, { method: "POST" })
    .then(() => {
      if (el) el.classList.remove("unread");
    })
    .catch((err) => console.error("Failed to mark notification read:", err));
}

// Toggle fullscreen on the video wrapper (works cross-browser, incl. Safari prefix)
function toggleVideoFullscreen() {
  const wrap = document.getElementById("videoWrap");
  const icon = document.getElementById("videoFullscreenIcon");
  if (!wrap) return;

  const isFullscreen = document.fullscreenElement || document.webkitFullscreenElement;

  if (!isFullscreen) {
    if (wrap.requestFullscreen) wrap.requestFullscreen();
    else if (wrap.webkitRequestFullscreen) wrap.webkitRequestFullscreen();
  } else {
    if (document.exitFullscreen) document.exitFullscreen();
    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
  }
}

["fullscreenchange", "webkitfullscreenchange"].forEach((evt) => {
  document.addEventListener(evt, () => {
    const icon = document.getElementById("videoFullscreenIcon");
    if (!icon) return;
    const isFullscreen = document.fullscreenElement || document.webkitFullscreenElement;
    icon.className = isFullscreen ? "fa-solid fa-compress" : "fa-solid fa-expand";
  });
});

document.addEventListener("DOMContentLoaded", () => {
  // Auto-dismiss flash messages after 4 seconds
  document.querySelectorAll(".alert-dismissible").forEach((alert) => {
    setTimeout(() => {
      if (window.bootstrap) {
        const bsAlert = window.bootstrap.Alert.getOrCreateInstance(alert);
        bsAlert.close();
      }
    }, 4000);
  });
});
