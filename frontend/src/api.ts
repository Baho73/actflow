// FILE: frontend/src/api.ts
// VERSION: 1.0.0
// START_MODULE_CONTRACT
//   PURPOSE: Типизированный клиент /api.
//   SCOPE: Типы DTO и вызовы. Никаких расчётов — статусы и суммы приходят с сервера.
//   LAYER: UI
//   DEPENDS: M-API
//   LINKS: M-UI
// END_MODULE_CONTRACT
//
// START_MODULE_MAP
//   api - методы дашборда
//   типы Payment, Totals, ProjectSummary, ImportReport, Project, Client, Filters
// END_MODULE_MAP
//
// START_CHANGE_SUMMARY
//   LAST_CHANGE: [v1.0.0 - Initial implementation]
// END_CHANGE_SUMMARY

export class ApiError extends Error {}

export type ActStatus = "not_sent" | "awaiting_signature" | "closed" | "needs_attention";
export type BindingMethod = "by_contract" | "by_client_service" | "manual" | "unbound";

export interface Payment {
  id: number;
  payment_date: string;
  amount: string;
  client_id: number;
  client_name: string;
  client_inn: string;
  project_id: number | null;
  project_name: string | null;
  binding_method: BindingMethod;
  conflict_reason: string | null;
  stage_mismatch: boolean;
  service_stages: string[];
  invoice_numbers: string[];
  contract_number: string | null;
  doc_number: string;
  purpose_text: string;
  is_sent: boolean;
  sent_at: string | null;
  is_signed: boolean;
  signed_at: string | null;
  manager_comment: string;
  act_status: ActStatus;
}

export interface Totals {
  total_amount: string;
  payments_count: number;
  projects_count: number;
  closed_amount: string;
  open_amount: string;
  needs_attention_amount: string;
  closed_count: number;
  not_sent_count: number;
  awaiting_count: number;
  needs_attention_count: number;
}

export interface ProjectSummary {
  project_id: number | null;
  project_name: string;
  payments_count: number;
  total: string;
  sent_count: number;
  signed_count: number;
  closed_ratio: string | null;
}

export interface Dashboard {
  totals: Totals;
  by_project: ProjectSummary[];
}

export interface SkippedGroup {
  code: string;
  text: string;
  count: number;
  amount: string;
}

export interface ImportReport {
  imported: number;
  already_known: number;
  skipped: SkippedGroup[];
  created_projects: number;
  unbound: number;
}

export interface Project {
  id: number;
  name: string;
  client_id: number;
  client_name: string;
  contract_number: string | null;
  service_stage: string | null;
  auto_created: boolean;
}

export interface Client {
  id: number;
  name: string;
  inn: string;
}

export interface Filters {
  project_id?: number | "";
  client_id?: number | "";
  date_from?: string;
  date_to?: string;
  service_stage?: string;
  act_status?: string;
  unbound_only?: boolean;
  search?: string;
  as_of?: string;
}

function qs(filters: Filters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== "" && v !== false) params.set(k, String(v));
  });
  return params.toString();
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let message = `Ошибка ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  importStatement: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportReport>("/api/import/statement", { method: "POST", body: form });
  },
  payments: (f: Filters, limit = 500) =>
    request<{ items: Payment[]; total: number }>(`/api/payments?${qs(f)}&limit=${limit}`),
  summary: (f: Filters) => request<Dashboard>(`/api/summary?${qs(f)}`),
  projects: () => request<Project[]>("/api/projects"),
  clients: () => request<Client[]>("/api/clients"),
  patchAct: (id: number, patch: { is_sent?: boolean; is_signed?: boolean; manager_comment?: string }, as_of?: string) =>
    request<Payment>(`/api/payments/${id}/act?${qs({ as_of })}`, json("PATCH", patch)),
  bulkAct: (ids: number[], patch: { is_sent?: boolean; is_signed?: boolean }, as_of?: string) =>
    request<{ updated: number }>(`/api/payments/bulk-act?${qs({ as_of })}`, json("POST", { payment_ids: ids, ...patch })),
  bindProject: (id: number, project_id: number | null, as_of?: string) =>
    request<Payment>(`/api/payments/${id}/project?${qs({ as_of })}`, json("PATCH", { project_id })),
  renameProject: (id: number, name: string) =>
    request<Project>(`/api/projects/${id}`, json("PATCH", { name })),
  exportUrl: (f: Filters) => `/api/export.csv?${qs(f)}`,
};
