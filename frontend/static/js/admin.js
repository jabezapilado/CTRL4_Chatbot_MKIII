/* Administrator account-management portal. Server-side RBAC remains authoritative. */

const ADMIN_API_BASE = window.location.origin;
let programs = [];

const accountListBody = document.getElementById("account-list-body");
const accountListMessage = document.getElementById("account-list-message");
const programCatalogMessage = document.getElementById(
  "program-catalog-message",
);
const accountFilterForm = document.getElementById("account-filter-form");
const accountSearch = document.getElementById("account-search");
const accountRoleFilter = document.getElementById("account-role-filter");
const accountStatusFilter = document.getElementById("account-status-filter");
const accountDialog = document.getElementById("account-dialog");
const accountForm = document.getElementById("account-form");
const accountFormMessage = document.getElementById("account-form-message");
const accountRole = document.getElementById("account-role");
const accountProgram = document.getElementById("account-program");
const accountAssignedPrograms = document.getElementById(
  "account-assigned-programs",
);
const studentProfileFields = document.getElementById("student-profile-fields");
const staffProfileFields = document.getElementById("staff-profile-fields");
const accountPasswordField = document.getElementById("account-password-field");
const accountPassword = document.getElementById("account-password");
const accountFormSubmit = document.getElementById("account-form-submit");
const accountImportDialog = document.getElementById("account-import-dialog");
const accountImportForm = document.getElementById("account-import-form");
const accountImportMessage = document.getElementById("account-import-message");
const accountImportFile = document.getElementById("account-import-file");
const accountImportSubmit = document.getElementById("account-import-submit");
const studentPasswordResetDialog = document.getElementById(
  "student-password-reset-dialog",
);
const studentPasswordResetForm = document.getElementById(
  "student-password-reset-form",
);
const studentPasswordResetMessage = document.getElementById(
  "student-password-reset-message",
);
const studentPasswordResetAccount = document.getElementById(
  "student-password-reset-account",
);
const studentPasswordResetNewPassword = document.getElementById(
  "student-reset-new-password",
);
const studentPasswordResetConfirmPassword = document.getElementById(
  "student-reset-confirm-password",
);
const studentPasswordResetSubmit = document.getElementById(
  "student-password-reset-submit",
);
const programDialog = document.getElementById("program-dialog");
const programForm = document.getElementById("program-form");
const programFormMessage = document.getElementById("program-form-message");
const programCode = document.getElementById("program-code");
const programDisplayName = document.getElementById("program-display-name");
const programFormSubmit = document.getElementById("program-form-submit");
const sortCollator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

let editingAccount = null;
let editingProgram = null;
let accountSort = { key: "account_number", direction: "asc" };
let programSort = { key: "display_name", direction: "asc" };
let loadedAccounts = [];
let loadedProgramCatalog = [];
let resettingStudentAccount = null;
const ADMIN_TABLE_PAGE_SIZE = 8;
const adminTablePages = new Map();

function accountNumber(account) {
  return account.student_number || account.staff_number || "—";
}

function parseList(value) {
  if (Array.isArray(value)) return value;
  if (typeof value !== "string" || !value.trim()) return [];

  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function accountPrograms(account) {
  if (account.role === "student") return account.program || "—";
  if (account.role === "staff") {
    const programs = parseList(account.assigned_programs);
    return programs.length ? programs.join(", ") : "—";
  }
  return "—";
}

function roleLabel(role) {
  return (
    {
      student: "Student",
      staff: "Guidance staff",
      admin: "Administrator",
    }[role] || "Unknown"
  );
}

function setFeedback(element, message = "", type = "") {
  element.textContent = message;
  element.classList.toggle("is-error", type === "error");
  element.classList.toggle("is-success", type === "success");
}

function appendAccountCell(row, value, label) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  cell.textContent = value || "—";
  row.appendChild(cell);
  return cell;
}

function renderAccountSummary(accounts) {
  const counts = accounts.reduce(
    (summary, account) => {
      summary.total += 1;
      summary[account.role] = (summary[account.role] || 0) + 1;
      summary[account.status] = (summary[account.status] || 0) + 1;
      return summary;
    },
    { total: 0, student: 0, staff: 0, admin: 0, active: 0, disabled: 0 },
  );

  document.getElementById("account-summary-total").textContent = String(
    counts.total,
  );
  document.getElementById("account-summary-students").textContent = String(
    counts.student,
  );
  document.getElementById("account-summary-staff").textContent = String(
    counts.staff,
  );
  document.getElementById("account-summary-admins").textContent = String(
    counts.admin,
  );
  document.getElementById("account-summary-status").textContent =
    `${counts.active} / ${counts.disabled}`;
}

function renderAccountSummaryUnavailable() {
  [
    "account-summary-total",
    "account-summary-students",
    "account-summary-staff",
    "account-summary-admins",
    "account-summary-status",
  ].forEach((elementId) => {
    document.getElementById(elementId).textContent = "—";
  });
}

function createActionButton(label, className, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function sortRecords(records, sort, valueFor) {
  return [...records].sort((left, right) => {
    const leftValue = String(valueFor(left, sort.key) || "").trim();
    const rightValue = String(valueFor(right, sort.key) || "").trim();

    if (!leftValue && !rightValue) return 0;
    if (!leftValue) return 1;
    if (!rightValue) return -1;

    const comparison = sortCollator.compare(leftValue, rightValue);
    return sort.direction === "asc" ? comparison : -comparison;
  });
}

function clearAdminTablePagination(tbodyId) {
  const tbody = document.getElementById(tbodyId);
  const host = tbody?.closest("table")?.parentElement;
  const pager = host?.querySelector(
    `[data-table-pagination="${tbodyId}"]`,
  );
  pager?.remove();
  host?.classList.remove("is-paginated");
}

function resetAdminTablePage(tbodyId) {
  adminTablePages.set(tbodyId, 1);
}

function paginateAdminRows(tbodyId, rows, render) {
  const tbody = document.getElementById(tbodyId);
  const table = tbody?.closest("table");
  const host = table?.parentElement;
  const total = rows.length;
  const totalPages = Math.max(1, Math.ceil(total / ADMIN_TABLE_PAGE_SIZE));
  const requestedPage = adminTablePages.get(tbodyId) || 1;
  const page = Math.min(Math.max(1, requestedPage), totalPages);
  adminTablePages.set(tbodyId, page);

  const existingPager = host?.querySelector(
    `[data-table-pagination="${tbodyId}"]`,
  );
  if (totalPages <= 1 || !host || !table) {
    existingPager?.remove();
    host?.classList.remove("is-paginated");
  } else {
    host.classList.add("is-paginated");
    const pager = existingPager || document.createElement("nav");
    pager.className = "table-pagination";
    pager.dataset.tablePagination = tbodyId;
    pager.setAttribute("aria-label", "Table pagination");
    pager.replaceChildren();

    const previous = createActionButton("Previous", "btn btn-outline btn-sm", () => {
      adminTablePages.set(tbodyId, page - 1);
      render();
    });
    previous.disabled = page === 1;

    const summary = document.createElement("span");
    summary.className = "table-pagination-summary";
    const start = (page - 1) * ADMIN_TABLE_PAGE_SIZE + 1;
    const end = Math.min(page * ADMIN_TABLE_PAGE_SIZE, total);
    summary.textContent = `Showing ${start}–${end} of ${total} · Page ${page} of ${totalPages}`;

    const next = createActionButton("Next", "btn btn-outline btn-sm", () => {
      adminTablePages.set(tbodyId, page + 1);
      render();
    });
    next.disabled = page === totalPages;

    pager.append(previous, summary, next);
    if (!existingPager) table.after(pager);
  }

  const start = (page - 1) * ADMIN_TABLE_PAGE_SIZE;
  return rows.slice(start, start + ADMIN_TABLE_PAGE_SIZE);
}

function accountSortValue(account, key) {
  if (key === "account_number") {
    return account.student_number || account.staff_number || "";
  }
  if (key === "programs") return accountPrograms(account);
  return account[key] || "";
}

function updateSortControls(scope, sort) {
  document.querySelectorAll(`[data-${scope}-sort]`).forEach((button) => {
    const isCurrent = button.dataset[`${scope}Sort`] === sort.key;
    const direction = isCurrent ? sort.direction : "none";
    button.closest("th").setAttribute("aria-sort", direction === "none" ? "none" : direction === "asc" ? "ascending" : "descending");
    button.setAttribute(
      "aria-label",
      `${button.textContent.trim()}: ${isCurrent ? `${direction}ending` : "not sorted"}. Activate to sort.`,
    );
    button.dataset.direction = direction;
  });
}

function toggleSort(scope, key) {
  const currentSort = scope === "account" ? accountSort : programSort;
  const nextSort = {
    key,
    direction: currentSort.key === key && currentSort.direction === "asc" ? "desc" : "asc",
  };

  if (scope === "account") {
    accountSort = nextSort;
    resetAdminTablePage("account-list-body");
    renderAccounts(loadedAccounts);
    return;
  }

  programSort = nextSort;
  resetAdminTablePage("program-catalog-list");
  renderProgramCatalog(loadedProgramCatalog);
}

function renderAccounts(accounts) {
  renderAccountSummary(accounts);
  accountListBody.replaceChildren();
  updateSortControls("account", accountSort);

  if (!accounts.length) {
    clearAdminTablePagination("account-list-body");
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "admin-empty-state";
    cell.textContent = "No accounts match the selected filters.";
    row.appendChild(cell);
    accountListBody.appendChild(row);
    return;
  }

  const visibleAccounts = paginateAdminRows(
    "account-list-body",
    sortRecords(accounts, accountSort, accountSortValue),
    () => renderAccounts(accounts),
  );
  visibleAccounts.forEach((account) => {
    const row = document.createElement("tr");
    appendAccountCell(row, account.full_name, "Name");
    appendAccountCell(row, account.email, "Email");
    appendAccountCell(row, roleLabel(account.role), "Role");

    const statusCell = document.createElement("td");
    statusCell.dataset.label = "Status";
    const status = document.createElement("span");
    status.className = `admin-status admin-status--${
      account.status === "active" ? "active" : "disabled"
    }`;
    status.textContent = account.status === "active" ? "Active" : "Disabled";
    statusCell.appendChild(status);
    row.appendChild(statusCell);

    appendAccountCell(row, accountNumber(account), "Account number");
    appendAccountCell(
      row,
      accountPrograms(account),
      "Program / assigned programs",
    );

    const actionsCell = document.createElement("td");
    actionsCell.dataset.label = "Actions";
    const actions = document.createElement("div");
    actions.className = "admin-row-actions";
    actions.appendChild(
      createActionButton("Edit", "btn btn-outline btn-sm", () => {
        openAccountForm(account);
      }),
    );

    if (account.role === "student" && account.status === "active") {
      actions.appendChild(
        createActionButton("Reset password", "btn btn-outline btn-sm", () => {
          openStudentPasswordReset(account);
        }),
      );
    }

    if (account.status === "active") {
      actions.appendChild(
        createActionButton("Deactivate", "btn btn-outline btn-sm", () => {
          deactivateAccount(account);
        }),
      );
    }

    actionsCell.appendChild(actions);
    row.appendChild(actionsCell);
    accountListBody.appendChild(row);
  });
}

function accountQuery() {
  const params = new URLSearchParams();
  const query = accountSearch.value.trim();
  const role = accountRoleFilter.value;
  const status = accountStatusFilter.value;

  if (query) params.set("q", query);
  if (role) params.set("role", role);
  if (status) params.set("status", status);
  return params;
}

async function responsePayload(response, fallbackMessage) {
  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload.message || fallbackMessage);
  }
  return payload;
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function downloadCsv(filename, rows) {
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadStudentAccountTemplate() {
  const exampleProgram =
    programs[0]?.display_name || "Replace with an active program";
  downloadCsv("ctrl4-student-account-import-template.csv", [
    ["full_name", "email", "gender", "program"],
    [
      "Example Student",
      "example@student.hau.edu.ph",
      "Prefer not to say",
      exampleProgram,
    ],
  ]);
}

function downloadImportedCredentials(items) {
  downloadCsv("ctrl4-imported-student-credentials.csv", [
    ["full_name", "email", "student_number", "temporary_password"],
    ...items.map((item) => [
      item.full_name,
      item.email,
      item.student_number,
      item.temporary_password,
    ]),
  ]);
}

function openAccountImport() {
  accountImportForm.reset();
  setFeedback(accountImportMessage);
  accountImportDialog.showModal();
  accountImportFile.focus();
}

function closeAccountImport() {
  if (accountImportDialog.open) accountImportDialog.close();
}

async function importStudentAccounts(event) {
  event.preventDefault();
  const file = accountImportFile.files?.[0];
  if (!file) {
    setFeedback(accountImportMessage, "Select a CSV file.", "error");
    return;
  }

  accountImportSubmit.disabled = true;
  setFeedback(accountImportMessage, "Validating and importing accounts…");
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(
      `${ADMIN_API_BASE}/api/accounts/import/students`,
      { method: "POST", body: formData },
    );
    const result = await responsePayload(
      response,
      "Unable to import student accounts.",
    );
    const items = result.data?.items || [];
    if (!items.length) {
      throw new Error("The import returned no accounts.");
    }
    downloadImportedCredentials(items);
    closeAccountImport();
    await loadAccounts();
    setFeedback(accountListMessage, result.message, "success");
  } catch (error) {
    setFeedback(
      accountImportMessage,
      error.message || "Unable to import student accounts.",
      "error",
    );
  } finally {
    accountImportSubmit.disabled = false;
  }
}

async function loadAccounts() {
  const params = accountQuery();
  setFeedback(accountListMessage, "Loading accounts…");

  try {
    const response = await fetch(
      `${ADMIN_API_BASE}/api/accounts${params.size ? `?${params}` : ""}`,
    );
    const payload = await responsePayload(
      response,
      "Unable to retrieve accounts.",
    );
    loadedAccounts = payload.data?.items || [];
    resetAdminTablePage("account-list-body");
    renderAccounts(loadedAccounts);
    setFeedback(accountListMessage);
  } catch (error) {
    accountListBody.replaceChildren();
    renderAccountSummaryUnavailable();
    setFeedback(
      accountListMessage,
      error.message || "Unable to retrieve accounts.",
      "error",
    );
  }
}

function populateProgramSelect() {
  accountProgram.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "Select program";
  accountProgram.appendChild(empty);

  programs.forEach((program) => {
    const option = document.createElement("option");
    option.value = program.display_name;
    option.textContent = program.display_name;
    accountProgram.appendChild(option);
  });
}

function renderAssignedPrograms(selectedPrograms = []) {
  const selected = new Set(selectedPrograms);
  accountAssignedPrograms.replaceChildren();

  programs.forEach((program) => {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "assigned_programs";
    checkbox.value = program.display_name;
    checkbox.checked = selected.has(program.display_name);
    const text = document.createElement("span");
    text.textContent = program.display_name;
    label.append(checkbox, text);
    accountAssignedPrograms.appendChild(label);
  });
}

function renderProgramCatalog(catalog) {
  const list = document.getElementById("program-catalog-list");
  list.replaceChildren();
  updateSortControls("program", programSort);

  if (!catalog.length) {
    clearAdminTablePagination("program-catalog-list");
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "admin-empty-state";
    cell.textContent = "No programs are configured.";
    row.appendChild(cell);
    list.appendChild(row);
    return;
  }

  const visiblePrograms = paginateAdminRows(
    "program-catalog-list",
    sortRecords(catalog, programSort, (program, key) => program[key]),
    () => renderProgramCatalog(catalog),
  );
  visiblePrograms.forEach((program) => {
    const row = document.createElement("tr");
    const toggle = createActionButton(
      program.active ? "Deactivate" : "Activate",
      "btn btn-outline btn-sm",
      () => void updateProgram(program.code, { active: !program.active }),
    );
    const edit = createActionButton("Edit", "btn btn-outline btn-sm", () => {
      openProgramForm(program);
    });

    appendAccountCell(row, program.display_name, "Program");
    appendAccountCell(row, program.code, "Program code");

    const statusCell = document.createElement("td");
    statusCell.dataset.label = "Status";
    const status = document.createElement("span");
    status.className = `admin-status admin-status--${
      program.active ? "active" : "disabled"
    }`;
    status.textContent = program.active ? "Active" : "Inactive";
    statusCell.appendChild(status);
    row.appendChild(statusCell);

    const actionsCell = document.createElement("td");
    actionsCell.dataset.label = "Actions";
    const actions = document.createElement("div");
    actions.className = "admin-row-actions";
    actions.append(edit, toggle);
    actionsCell.appendChild(actions);
    row.appendChild(actionsCell);
    list.appendChild(row);
  });
}

async function loadPrograms() {
  setFeedback(programCatalogMessage, "Loading program catalog…");
  try {
    const response = await fetch(`${ADMIN_API_BASE}/api/accounts/programs`);
    const payload = await responsePayload(
      response,
      "Unable to retrieve programs.",
    );
    loadedProgramCatalog = payload.data?.items || [];
    resetAdminTablePage("program-catalog-list");
    programs = loadedProgramCatalog.filter((program) => program.active);
    populateProgramSelect();
    renderAssignedPrograms(
      editingAccount ? parseList(editingAccount.assigned_programs) : [],
    );
    renderProgramCatalog(loadedProgramCatalog);
    setFeedback(programCatalogMessage);
  } catch (error) {
    programs = [];
    loadedProgramCatalog = [];
    populateProgramSelect();
    renderAssignedPrograms();
    setFeedback(
      programCatalogMessage,
      error.message || "Unable to retrieve programs.",
      "error",
    );
  }
}

async function updateProgram(code, updates) {
  try {
    const response = await fetch(
      `${ADMIN_API_BASE}/api/accounts/programs/${encodeURIComponent(code)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      },
    );
    const payload = await responsePayload(
      response,
      "Unable to update program.",
    );
    setFeedback(programCatalogMessage, payload.message, "success");
    await loadPrograms();
  } catch (error) {
    setFeedback(
      programCatalogMessage,
      error.message || "Unable to update program.",
      "error",
    );
  }
}

function setProgramFormValues(program = null) {
  editingProgram = program;
  programForm.reset();
  programCode.disabled = Boolean(program);

  if (program) {
    document.getElementById("program-dialog-kicker").textContent =
      "Existing program";
    document.getElementById("program-dialog-title").textContent =
      "Edit program";
    document.getElementById("program-code-help").textContent =
      "Program codes cannot be changed after creation.";
    programCode.value = program.code;
    programDisplayName.value = program.display_name;
    programFormSubmit.textContent = "Save changes";
  } else {
    document.getElementById("program-dialog-kicker").textContent =
      "New program";
    document.getElementById("program-dialog-title").textContent =
      "Create program";
    document.getElementById("program-code-help").textContent =
      "Use uppercase letters, numbers, underscores, or hyphens.";
    programFormSubmit.textContent = "Create program";
  }

  setFeedback(programFormMessage);
}

function openProgramForm(program = null) {
  setProgramFormValues(program);
  programDialog.showModal();
  (program ? programDisplayName : programCode).focus();
}

function closeProgramForm() {
  if (programDialog.open) programDialog.close();
}

async function saveProgram(event) {
  event.preventDefault();
  const isEdit = Boolean(editingProgram);
  const payload = isEdit
    ? { display_name: programDisplayName.value.trim() }
    : {
        code: programCode.value.trim(),
        display_name: programDisplayName.value.trim(),
      };

  if (!payload.display_name || (!isEdit && !payload.code)) {
    setFeedback(programFormMessage, "Complete all required fields.", "error");
    return;
  }

  programFormSubmit.disabled = true;
  setFeedback(
    programFormMessage,
    isEdit ? "Saving changes…" : "Creating program…",
  );

  try {
    const response = await fetch(
      `${ADMIN_API_BASE}${
        isEdit
          ? `/api/accounts/programs/${encodeURIComponent(editingProgram.code)}`
          : "/api/accounts/programs"
      }`,
      {
        method: isEdit ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    const result = await responsePayload(
      response,
      isEdit ? "Unable to update program." : "Unable to create program.",
    );
    closeProgramForm();
    await loadPrograms();
    setFeedback(programCatalogMessage, result.message, "success");
  } catch (error) {
    setFeedback(
      programFormMessage,
      error.message ||
        (isEdit ? "Unable to update program." : "Unable to create program."),
      "error",
    );
  } finally {
    programFormSubmit.disabled = false;
  }
}

function syncRoleFields() {
  const role = accountRole.value;
  const editing = Boolean(editingAccount);
  studentProfileFields.hidden = role !== "student";
  staffProfileFields.hidden = role !== "staff";
  accountPasswordField.hidden = editing;
  accountPassword.required = !editing;
  accountRole.disabled = editing;
}

function setFormValues(account = null) {
  editingAccount = account;
  accountForm.reset();
  populateProgramSelect();

  if (account) {
    document.getElementById("account-dialog-kicker").textContent =
      "Existing account";
    document.getElementById("account-dialog-title").textContent =
      "Edit account";
    accountFormSubmit.textContent = "Save changes";
    document.getElementById("account-full-name").value =
      account.full_name || "";
    document.getElementById("account-email").value = account.email || "";
    document.getElementById("account-gender").value = account.gender || "";
    accountRole.value = account.role || "student";
    accountProgram.value = account.program || "";
    renderAssignedPrograms(parseList(account.assigned_programs));
  } else {
    document.getElementById("account-dialog-kicker").textContent =
      "New account";
    document.getElementById("account-dialog-title").textContent =
      "Create account";
    accountFormSubmit.textContent = "Create account";
    accountRole.value = "student";
    renderAssignedPrograms();
  }

  syncRoleFields();
  setFeedback(accountFormMessage);
}

function openAccountForm(account = null) {
  setFormValues(account);
  accountDialog.showModal();
  document.getElementById("account-full-name").focus();
}

function closeAccountForm() {
  if (accountDialog.open) accountDialog.close();
}

function openStudentPasswordReset(account) {
  resettingStudentAccount = account;
  studentPasswordResetForm.reset();
  studentPasswordResetAccount.textContent = `Set a new temporary password for ${account.full_name || "this student"}.`;
  setFeedback(studentPasswordResetMessage);
  studentPasswordResetDialog.showModal();
  studentPasswordResetNewPassword.focus();
}

function closeStudentPasswordReset() {
  if (studentPasswordResetDialog.open) studentPasswordResetDialog.close();
  resettingStudentAccount = null;
}

function updateStudentPasswordResetButton() {
  const passwordsMatch =
    studentPasswordResetNewPassword.value === studentPasswordResetConfirmPassword.value;
  studentPasswordResetSubmit.disabled = !(
    studentPasswordResetNewPassword.value.length >= 8 &&
    studentPasswordResetConfirmPassword.value &&
    passwordsMatch
  );
}

async function submitStudentPasswordReset(event) {
  event.preventDefault();
  if (!resettingStudentAccount || studentPasswordResetSubmit.disabled) return;

  studentPasswordResetSubmit.disabled = true;
  setFeedback(studentPasswordResetMessage, "Resetting password…");
  try {
    const response = await fetch(
      `${ADMIN_API_BASE}/api/accounts/${resettingStudentAccount.id}/password`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          new_password: studentPasswordResetNewPassword.value,
          confirm_password: studentPasswordResetConfirmPassword.value,
        }),
      },
    );
    const result = await responsePayload(response, "Unable to reset student password.");
    closeStudentPasswordReset();
    setFeedback(accountListMessage, result.message, "success");
  } catch (error) {
    setFeedback(
      studentPasswordResetMessage,
      error.message || "Unable to reset student password.",
      "error",
    );
  } finally {
    updateStudentPasswordResetButton();
  }
}

function formRole() {
  return editingAccount?.role || accountRole.value;
}

function selectedPrograms() {
  return Array.from(
    accountAssignedPrograms.querySelectorAll(
      'input[name="assigned_programs"]:checked',
    ),
    (checkbox) => checkbox.value,
  );
}

function accountPayload() {
  const role = formRole();
  const payload = {
    full_name: document.getElementById("account-full-name").value.trim(),
    email: document.getElementById("account-email").value.trim(),
    gender: document.getElementById("account-gender").value,
  };

  if (!payload.full_name || !payload.email || !payload.gender) {
    throw new Error("Full name, email address, and gender are required.");
  }

  if (!editingAccount) {
    const password = accountPassword.value;
    if (!password) throw new Error("A temporary password is required.");
    payload.password = password;
    payload.role = role;
  }

  if (role === "student") {
    payload.program = accountProgram.value;
    if (!payload.program) throw new Error("A student program is required.");
  }

  if (role === "staff") {
    payload.assigned_programs = selectedPrograms();
  }

  return payload;
}

function accountEndpoint(account) {
  if (account.role === "staff") return `/api/accounts/staff/${account.id}`;
  if (account.role === "admin") return `/api/accounts/admin/${account.id}`;
  return `/api/accounts/${account.id}`;
}

async function saveAccount(event) {
  event.preventDefault();
  let payload;
  try {
    payload = accountPayload();
  } catch (error) {
    setFeedback(accountFormMessage, error.message, "error");
    return;
  }

  const isEdit = Boolean(editingAccount);
  accountFormSubmit.disabled = true;
  setFeedback(
    accountFormMessage,
    isEdit ? "Saving changes…" : "Creating account…",
  );

  try {
    const response = await fetch(
      `${ADMIN_API_BASE}${isEdit ? accountEndpoint(editingAccount) : "/api/accounts"}`,
      {
        method: isEdit ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    const result = await responsePayload(
      response,
      isEdit ? "Unable to update account." : "Unable to create account.",
    );
    closeAccountForm();
    setFeedback(accountListMessage, result.message, "success");
    await loadAccounts();
    setFeedback(accountListMessage, result.message, "success");
  } catch (error) {
    setFeedback(
      accountFormMessage,
      error.message ||
        (isEdit ? "Unable to update account." : "Unable to create account."),
      "error",
    );
  } finally {
    accountFormSubmit.disabled = false;
  }
}

async function deactivateAccount(account) {
  const confirmed = window.confirm(
    "Deactivate this account? A disabled account cannot sign in, and this portal does not provide reactivation.",
  );
  if (!confirmed) return;

  setFeedback(accountListMessage, "Deactivating account…");
  try {
    const response = await fetch(
      `${ADMIN_API_BASE}${accountEndpoint(account)}`,
      { method: "DELETE" },
    );
    const result = await responsePayload(
      response,
      "Unable to deactivate account.",
    );
    await loadAccounts();
    setFeedback(accountListMessage, result.message, "success");
  } catch (error) {
    setFeedback(
      accountListMessage,
      error.message || "Unable to deactivate account.",
      "error",
    );
  }
}

function resetFilters() {
  accountFilterForm.reset();
  loadAccounts();
}

document.getElementById("create-account-btn").addEventListener("click", () => {
  openAccountForm();
});
document
  .getElementById("download-account-template-btn")
  .addEventListener("click", downloadStudentAccountTemplate);
document
  .getElementById("import-accounts-btn")
  .addEventListener("click", openAccountImport);
document
  .getElementById("account-import-close")
  .addEventListener("click", closeAccountImport);
document
  .getElementById("account-import-cancel")
  .addEventListener("click", closeAccountImport);
document.getElementById("create-program-btn").addEventListener("click", () => {
  openProgramForm();
});
document
  .getElementById("account-reset-btn")
  .addEventListener("click", resetFilters);
document
  .getElementById("account-dialog-close")
  .addEventListener("click", closeAccountForm);
document
  .getElementById("account-form-cancel")
  .addEventListener("click", closeAccountForm);
document
  .getElementById("program-dialog-close")
  .addEventListener("click", closeProgramForm);
document
  .getElementById("program-form-cancel")
  .addEventListener("click", closeProgramForm);
accountRole.addEventListener("change", () => {
  renderAssignedPrograms();
  syncRoleFields();
});
accountFilterForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadAccounts();
});
document.querySelectorAll("[data-account-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    toggleSort("account", button.dataset.accountSort);
  });
});
document.querySelectorAll("[data-program-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    toggleSort("program", button.dataset.programSort);
  });
});
accountForm.addEventListener("submit", saveAccount);
accountImportForm.addEventListener("submit", importStudentAccounts);
accountDialog.addEventListener("click", (event) => {
  if (event.target === accountDialog) closeAccountForm();
});
accountImportDialog.addEventListener("click", (event) => {
  if (event.target === accountImportDialog) closeAccountImport();
});
studentPasswordResetForm.addEventListener("submit", submitStudentPasswordReset);
studentPasswordResetDialog.addEventListener("click", (event) => {
  if (event.target === studentPasswordResetDialog) closeStudentPasswordReset();
});
document
  .getElementById("student-password-reset-close")
  .addEventListener("click", closeStudentPasswordReset);
document
  .getElementById("student-password-reset-cancel")
  .addEventListener("click", closeStudentPasswordReset);
[studentPasswordResetNewPassword, studentPasswordResetConfirmPassword].forEach(
  (input) => input.addEventListener("input", updateStudentPasswordResetButton),
);
programForm.addEventListener("submit", saveProgram);
programDialog.addEventListener("click", (event) => {
  if (event.target === programDialog) closeProgramForm();
});
document.getElementById("admin-logout-btn").addEventListener("click", () => {
  window.logout();
});

void loadPrograms();
loadAccounts();
updateStudentPasswordResetButton();
