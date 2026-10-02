// Legacy GBSA ERP System App JS

let attendanceData = [];
let allEmployeesList = [];
let selectedRowIndex = -1;
let selectedEmployeeId = null;

document.addEventListener("DOMContentLoaded", () => {
    initClock();
    initEmployeeOptions();
    loadAttendanceLogs();

    // 5초마다 조용히 백그라운드 자동 갱신 (다른 PC/대시보드 변동사항 실시간 동기화)
    setInterval(() => {
        loadAttendanceLogs(true);
    }, 5000);
});

// Live clock
function initClock() {
    const update = () => {
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const hh = String(now.getHours()).padStart(2, '0');
        const mi = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        const el = document.getElementById("currentClock");
        if (el) el.textContent = `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
    };
    update();
    setInterval(update, 1000);
}

function getTodayDateString() {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
}

function getCurrentTimeString() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mi = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    return `${hh}:${mi}:${ss}`;
}

// Fetch employee list for select dropdown
async function initEmployeeOptions() {
    try {
        const res = await fetch(`/api/employees?_t=${Date.now()}`, { cache: "no-store" });
        const json = await res.json();
        if (json.success && json.employees) {
            allEmployeesList = json.employees;
            const selectEl = document.getElementById("empSelect");
            if (selectEl) {
                const curVal = selectEl.value;
                selectEl.innerHTML = `<option value="">[전체] 등록된 사원 전체 보기</option>`;
                allEmployeesList.forEach(emp => {
                    const opt = document.createElement("option");
                    opt.value = emp.emp_id;
                    const pos = emp.position ? ` ${emp.position}` : '';
                    opt.textContent = `[${emp.dept_name}] ${emp.emp_name}${pos} (${emp.emp_id})`;
                    selectEl.appendChild(opt);
                });
                if (curVal) selectEl.value = curVal;
            }
        }
    } catch (err) {
        console.error("Employee list load error:", err);
    }
}

// Handle Employee Select Box Change
function handleEmpSelectChange() {
    const selectEl = document.getElementById("empSelect");
    const empId = selectEl.value;
    selectedRowIndex = -1;

    if (empId) {
        selectedEmployeeId = empId;
        const matched = allEmployeesList.find(e => e.emp_id === empId);
        if (matched) {
            document.getElementById("empName").value = matched.emp_name;
            updateUserDisplay(matched.emp_name, matched.dept_name);
        }
    } else {
        selectedEmployeeId = null;
        document.getElementById("empName").value = "";
        updateUserDisplay("전체 사원", "3개 부서");
    }

    loadAttendanceLogs();
}

// Handle Employee Name Text Input
function handleEmpNameInput() {
    const nameVal = document.getElementById("empName").value.trim();
    const selectEl = document.getElementById("empSelect");
    selectedRowIndex = -1;

    if (nameVal) {
        const matched = allEmployeesList.find(e => e.emp_name === nameVal || e.emp_id === nameVal);
        if (matched) {
            selectedEmployeeId = matched.emp_id;
            selectEl.value = matched.emp_id;
            updateUserDisplay(matched.emp_name, matched.dept_name);
        } else {
            selectedEmployeeId = null;
            selectEl.value = "";
            updateUserDisplay(nameVal, "검색 사원");
        }
    } else {
        selectedEmployeeId = null;
        selectEl.value = "";
        updateUserDisplay("전체 사원", "3개 부서");
    }

    loadAttendanceLogs();
}

// Update Top User Info Header Bar
function updateUserDisplay(empName, deptName) {
    const displayEl = document.getElementById("currentUserDisplay");
    if (displayEl) {
        displayEl.innerHTML = `사용자: <strong>${empName} (${deptName})</strong>`;
    }
}

// Fetch logs from backend
async function loadAttendanceLogs(silent = false) {
    const tbody = document.getElementById("gridTbody");
    if (!silent) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center" style="padding: 20px; color: #666;">
                    <i class="fa-solid fa-spinner fa-spin"></i> 데이터를 조회하는 중입니다...
                </td>
            </tr>
        `;
    }

    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const empName = document.getElementById("empName").value;

    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (empName) params.append("emp_name", empName);
    params.append("_t", Date.now().toString());

    try {
        const res = await fetch(`/api/attendance/logs?${params.toString()}`, { cache: "no-store" });
        const json = await res.json();

        if (json.success) {
            attendanceData = json.data;
            const recEl = document.getElementById("recordCount");
            if (recEl) recEl.textContent = attendanceData.length;
            renderGridTable();
        } else {
            if (!silent) tbody.innerHTML = `<tr><td colspan="10" class="text-center" style="color: red; padding: 20px;">데이터 조회 오류가 발생했습니다.</td></tr>`;
        }
    } catch (err) {
        console.error("API Error:", err);
        if (!silent) tbody.innerHTML = `<tr><td colspan="10" class="text-center" style="color: red; padding: 20px;">서버 통신 장애: ${err.message}</td></tr>`;
    }
}

// Render 10-column Excel Table Grid
function renderGridTable() {
    const tbody = document.getElementById("gridTbody");

    if (attendanceData.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center" style="padding: 25px; color: #888;">
                    조회 조건에 해당하는 근태 리더기 내역이 없습니다.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = attendanceData.map((row, index) => {
        const isSelected = selectedRowIndex === index;
        const selectedClass = isSelected ? "selected-row" : "";

        return `
            <tr class="${selectedClass}" onclick="selectGridRow(${index}, '${row.emp_id}', '${row.emp_name}', '${row.dept_name}')">
                <td class="text-center">${row.no}</td>
                <td class="text-center">${row.work_date}</td>
                <td class="text-center font-bold">${row.emp_name}</td>
                <td class="text-center">${row.emp_id}</td>
                <td class="text-left">${row.dept_name}</td>
                <td class="text-center font-mono">${row.card_number}</td>
                <td class="text-center">${row.work_type}</td>
                <td class="text-center">${row.work_shape}</td>
                <td class="text-center font-mono" style="${!row.check_in_time ? 'color:#e74c3c; font-weight:bold;' : ''}">${row.check_in_time || '-'}</td>
                <td class="text-center font-mono" style="${!row.check_out_time ? 'color:#9b59b6; font-weight:bold;' : ''}">${row.check_out_time || '-'}</td>
            </tr>
        `;
    }).join("");
}

// Row Click Selection
function selectGridRow(index, empId, empName, deptName) {
    selectedRowIndex = index;
    selectedEmployeeId = empId;
    
    document.getElementById("empName").value = empName;
    const selectEl = document.getElementById("empSelect");
    if (selectEl) selectEl.value = empId;

    updateUserDisplay(empName, deptName);
    renderGridTable();
}

// Get targeted employee ID (selected row or text input/select)
function getTargetEmpId() {
    if (selectedEmployeeId) return selectedEmployeeId;

    const selectEl = document.getElementById("empSelect");
    if (selectEl && selectEl.value) return selectEl.value;

    const inputName = document.getElementById("empName").value.trim();
    if (!inputName) return null;

    // Search matching emp in data
    const matched = attendanceData.find(r => r.emp_name === inputName || r.emp_id === inputName);
    if (matched) return matched.emp_id;

    const matchedGlobal = allEmployeesList.find(e => e.emp_name === inputName || e.emp_id === inputName);
    if (matchedGlobal) return matchedGlobal.emp_id;

    return "GBSA2018012";
}

// Handle Check-in Action
async function handleCheckIn() {
    const empId = getTargetEmpId();
    if (!empId) {
        showErpAlert("출근 처리할 사원을 선택하거나 사원명을 입력해주세요.");
        return;
    }

    const workDate = getTodayDateString();
    const checkInTime = getCurrentTimeString();

    // 조회 종료일자가 오늘보다 이전이면 오늘로 자동 확장하여 즉시 보이도록 처리
    const endInput = document.getElementById("endDate");
    if (endInput && endInput.value < workDate) {
        endInput.value = workDate;
    }

    try {
        const res = await fetch("/api/attendance/check-in", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                emp_id: empId,
                work_date: workDate,
                check_in_time: checkInTime
            })
        });

        const json = await res.json();
        if (json.success) {
            showErpAlert(json.message);
            await loadAttendanceLogs();
        } else {
            showErpAlert("출근 처리 중 오류 발생");
        }
    } catch (err) {
        showErpAlert(`통신 오류: ${err.message}`);
    }
}

// Handle Check-out Action
async function handleCheckOut() {
    const empId = getTargetEmpId();
    if (!empId) {
        showErpAlert("퇴근 처리할 사원을 선택하거나 사원명을 입력해주세요.");
        return;
    }

    const workDate = getTodayDateString();
    const checkOutTime = getCurrentTimeString();

    // 조회 종료일자가 오늘보다 이전이면 오늘로 자동 확장
    const endInput = document.getElementById("endDate");
    if (endInput && endInput.value < workDate) {
        endInput.value = workDate;
    }

    try {
        const res = await fetch("/api/attendance/check-out", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                emp_id: empId,
                work_date: workDate,
                check_out_time: checkOutTime
            })
        });

        const json = await res.json();
        if (json.success) {
            showErpAlert(json.message);
            await loadAttendanceLogs();
        } else {
            showErpAlert("퇴근 처리 중 오류 발생");
        }
    } catch (err) {
        showErpAlert(`통신 오류: ${err.message}`);
    }
}

// Download Excel File
function downloadExcel() {
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const empName = document.getElementById("empName").value;

    const params = new URLSearchParams();
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    if (empName) params.append("emp_name", empName);
    params.append("_t", Date.now().toString());

    window.location.href = `/api/attendance/export/excel?${params.toString()}`;
    showErpAlert("엑셀 파일 다운로드가 시작되었습니다.");
}

// Alert Message Helper
function showErpAlert(msg) {
    const alertBox = document.getElementById("erpAlert");
    const alertMsg = document.getElementById("erpAlertMsg");
    if (alertBox && alertMsg) {
        alertMsg.textContent = msg;
        alertBox.classList.remove("hidden");
        setTimeout(() => {
            alertBox.classList.add("hidden");
        }, 3000);
    }
}
