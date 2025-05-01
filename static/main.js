let hasUnsavedChanges = false;
let minimumTime = 0;

window.onload = function() {
  updateStatus(); // already here

  // Attach input listener
  document.getElementById("min-time-input").addEventListener('input', () => {
    hasUnsavedChanges = true;
  });
};


window.addEventListener('beforeunload', function (e) {
  if (hasUnsavedChanges) {
    e.preventDefault();
    e.returnValue = '';
  }
});

async function updateStatus() {
  const settingsRes = await fetch('/api/get_settings');
  const settings = await settingsRes.json();
  const mode = settings.mode;

  // Show/Hide views
  if (mode === "camera") {
    document.getElementById("camera-view").style.display = "block";
    document.getElementById("rfid-view").style.display = "none";

    // Camera logic
    const response = await fetch('/api/status');
    const data = await response.json();
    if (data.next_battery === "None") {
      document.getElementById("next-battery").textContent = "No Batteries have reached the minimum charge time!";
    } else {
      document.getElementById("next-battery").textContent = data.next_battery;
    }
    const list = document.getElementById("battery-list");
    list.innerHTML = '';
    data.batteries.forEach(b => {
      const item = document.createElement('li');
      item.textContent = `Battery ${b.id}: ${b.time_charging}s`;
      list.appendChild(item);
    });

  } else if (mode === "rfid") {
    document.getElementById("camera-view").style.display = "none";
    document.getElementById("rfid-view").style.display = "block";

    const rfidRes = await fetch('/api/rfid/status');
    const rfidData = await rfidRes.json();

    document.getElementById("next-battery").textContent = "RFID Mode Active";

    const inList = document.getElementById("rfid-in-list");
    const outList = document.getElementById("rfid-out-list");

    inList.innerHTML = '';
    outList.innerHTML = '';

    rfidData.checked_in.forEach(tag => {
      const item = document.createElement('li');
      item.textContent = tag;
      inList.appendChild(item);
    });

    rfidData.checked_out.forEach(tag => {
      const item = document.createElement('li');
      item.textContent = tag;
      outList.appendChild(item);
    });
  }
}


function openModal() {
  fetch('/api/get_settings')
    .then(res => res.json())
    .then(data => {
      document.getElementById("min-time-input").value = data.minimum_time;
      document.getElementById("mode-select").value = data.mode;
    });
  document.getElementById("settings-modal").style.display = "block";
}

function closeModal() {
  document.getElementById("settings-modal").style.display = "none";
}


function updateSettings() {
  const minimumTime = parseInt(document.getElementById("min-time-input").value) || 0;
  const mode = document.getElementById("mode-select").value;

  fetch('/api/set_settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ minimum_time: minimumTime, mode: mode })
  });

  hasUnsavedChanges = false;
  closeModal();
}

setInterval(updateStatus, 2000);

function openHistory() {
  fetch('/api/rfid/history')
    .then(res => res.json())
    .then(data => {
      const container = document.getElementById("battery-history-list");
      container.innerHTML = '';
      Object.entries(data).forEach(([tag, info]) => {
        const item = document.createElement('div');
        const avg = info.usage_cycles > 0
          ? Math.round(info.total_charge_time / info.usage_cycles)
          : 0;
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

window.onclick = function(event) {
    if (event.target === document.getElementById("settings-modal")) {
      closeModal();
    }
    if (event.target === document.getElementById("history-modal")) {
      closeHistory();
    }
  };
  
