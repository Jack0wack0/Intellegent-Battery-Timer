let hasUnsavedChanges = false;

// ==== Firebase Init (from Flask) ====
firebase.initializeApp(window.firebaseConfig);
const db = firebase.database();

window.onload = function () {
  updateStatus();

  // Detect unsaved settings changes
  document.getElementById("min-time-input").addEventListener("input", () => {
    hasUnsavedChanges = true;
  });

  // Start listening for name requests
  listenForNameRequests();
};

window.addEventListener("beforeunload", function (e) {
  if (hasUnsavedChanges) {
    e.preventDefault();
    e.returnValue = "";
  }
});

// ====== STATUS UPDATES ======
async function updateStatus() {
  const settingsRes = await fetch("/api/get_settings");
  const settings = await settingsRes.json();
  const mode = settings.mode;

  if (mode === "camera") {
    document.getElementById("camera-view").style.display = "block";
    document.getElementById("rfid-view").style.display = "none";

    const response = await fetch("/api/status");
    const data = await response.json();
    if (data.next_battery === "None") {
      document.getElementById("next-battery").textContent =
        "No Batteries have reached the minimum charge time!";
    } else {
      document.getElementById("next-battery").textContent = data.next_battery;
    }
    const list = document.getElementById("battery-list");
    list.innerHTML = "";
    data.batteries.forEach((b) => {
      const item = document.createElement("li");
      item.textContent = `Battery ${b.id}: ${b.time_charging}s`;
      list.appendChild(item);
    });
  } else if (mode === "rfid") {
    document.getElementById("camera-view").style.display = "none";
    document.getElementById("rfid-view").style.display = "block";

    const rfidRes = await fetch("/api/rfid/status");
    const rfidData = await rfidRes.json();

    document.getElementById("next-battery").textContent = "RFID Mode Active";

    const inList = document.getElementById("rfid-in-list");
    const outList = document.getElementById("rfid-out-list");

    inList.innerHTML = "";
    outList.innerHTML = "";

    rfidData.checked_in.forEach((tag) => {
      const item = document.createElement("li");
      item.textContent = tag;
      inList.appendChild(item);
    });

    rfidData.checked_out.forEach((tag) => {
      const item = document.createElement("li");
      item.textContent = tag;
      outList.appendChild(item);
    });
  }
}
setInterval(updateStatus, 2000);

// ====== SETTINGS MODAL ======
function openModal() {
  fetch("/api/get_settings")
    .then((res) => res.json())
    .then((data) => {
      document.getElementById("min-time-input").value = data.minimum_time;
      document.getElementById("mode-select").value = data.mode;
    });
  document.getElementById("settings-modal").style.display = "block";
}

function closeModal() {
  document.getElementById("settings-modal").style.display = "none";
}

function updateSettings() {
  const minimumTime =
    parseInt(document.getElementById("min-time-input").value) || 0;
  const mode = document.getElementById("mode-select").value;

  fetch("/api/set_settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ minimum_time: minimumTime, mode: mode }),
  });

  hasUnsavedChanges = false;
  closeModal();
}

// ====== HISTORY MODAL ======
function openHistory() {
  fetch("/api/rfid/history")
    .then((res) => res.json())
    .then((data) => {
      const container = document.getElementById("battery-history-list");
      container.innerHTML = "";
      Object.entries(data).forEach(([tag, info]) => {
        const avg =
          info.usage_cycles > 0
            ? Math.round(info.total_charge_time / info.usage_cycles)
            : 0;
        const item = document.createElement("div");
        item.innerHTML = `
          <strong>${tag}</strong><br>
          Cycles: ${info.usage_cycles}<br>
          Avg Charge Time: ${avg}s<br><br>`;
        container.appendChild(item);
      });
    });
  document.getElementById("history-modal").style.display = "block";
}

function closeHistory() {
  document.getElementById("history-modal").style.display = "none";
}

// ====== NAME REQUEST LISTENER ======
function listenForNameRequests() {
  db.ref("NameRequests").on("child_added", (snapshot) => {
    const tagId = snapshot.key;
    const data = snapshot.val() || {};

    document.getElementById("name-tag-id").innerText = tagId;
    document.getElementById("name-tag-slot").innerText =
      data.Slot ?? "Unknown";
    document.getElementById("battery-name-input").value = "";

    document.getElementById("name-modal").style.display = "block";
  });
}

function submitBatteryName() {
  const tagId = document.getElementById("name-tag-id").innerText;
  const name = document.getElementById("battery-name-input").value.trim();

  if (!name) {
    alert("Please enter a battery name.");
    return;
  }

  fetch("/api/battery-name", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag_id: tagId, name: name }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.status === "success") {
        db.ref("NameRequests/" + tagId).remove();
        document.getElementById("name-modal").style.display = "none";
      } else {
        alert("Error saving name: " + (data.error || "Unknown error"));
      }
    })
    .catch((err) => {
      console.error(err);
      alert("Failed to save battery name.");
    });
}

// ====== CLICK OUTSIDE MODAL CLOSE ======
window.onclick = function (event) {
  if (event.target === document.getElementById("settings-modal")) {
    closeModal();
  }
  if (event.target === document.getElementById("history-modal")) {
    closeHistory();
  }
  if (event.target === document.getElementById("name-modal")) {
    document.getElementById("name-modal").style.display = "none";
  }
};
