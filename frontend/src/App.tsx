// FILE: frontend/src/App.tsx
// VERSION: 1.0.0
// START_MODULE_CONTRACT
//   PURPOSE: Дашборд: показатели, фильтры, таблица оплат, сводка по проектам, импорт выписки.
//   SCOPE: Только отображение и команды. Статусы и суммы приходят с сервера — фронт не считает.
//   LAYER: UI
//   DEPENDS: M-API
//   LINKS: M-UI, V-M-UI
// END_MODULE_CONTRACT
//
// START_MODULE_MAP
//   default - App: дашборд целиком
// END_MODULE_MAP
//
// START_CHANGE_SUMMARY
//   LAST_CHANGE: [v1.0.0 - Initial implementation]
// END_CHANGE_SUMMARY

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActStatus,
  Client,
  Dashboard,
  Filters,
  ImportReport,
  Payment,
  Project,
  api,
} from "./api";
import ImportPanel from "./components/ImportPanel";
import PaymentsTable from "./components/PaymentsTable";
import ProjectsSummary from "./components/ProjectsSummary";

const STATUS_LABEL: Record<ActStatus, string> = {
  not_sent: "Акт не отправлен",
  awaiting_signature: "Ожидает подписи",
  closed: "Закрыт",
  needs_attention: "Требует внимания",
};

// Выписка заканчивается 09.08.2026: если считать статусы «сегодня», всё будет просрочено
// и дашборд потеряет смысл. Демо-дата делает картину живой.
const DEMO_AS_OF = "2026-08-14";

function money(v: string | number): string {
  return Number(v).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function App() {
  const [tab, setTab] = useState<"payments" | "projects">("payments");
  const [filters, setFilters] = useState<Filters>({ as_of: DEMO_AS_OF });
  const [payments, setPayments] = useState<Payment[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const [p, d, pr, cl] = await Promise.all([
        api.payments(filters),
        api.summary(filters),
        api.projects(),
        api.clients(),
      ]);
      setPayments(p.items);
      setDashboard(d);
      setProjects(pr);
      setClients(cl);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  const services = useMemo(() => {
    const all = new Set<string>();
    payments.forEach((p) => p.service_stages.forEach((s) => all.add(s)));
    return [...all].sort();
  }, [payments]);

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters((f) => ({ ...f, [key]: value }));

  const t = dashboard?.totals;

  return (
    <>
      <header className="topbar">
        <span className="brand">ActFlow</span>
        <span className="tagline">оплаты, проекты и закрывающие документы</span>
        <span className="spacer" />
        <span className="muted" style={{ fontSize: 12 }}>
          статусы на {new Date(filters.as_of || DEMO_AS_OF).toLocaleDateString("ru-RU")}
        </span>
      </header>

      <main className="container">
        {error && <div className="banner error">{error}</div>}

        <ImportPanel
          onImported={(r) => {
            setReport(r);
            load();
          }}
          report={report}
          onError={setError}
        />

        {t && (
          <div className="kpis">
            <div className="kpi">
              <div className="label">Оплат</div>
              <div className="value">{t.payments_count}</div>
              <div className="sub">на {money(t.total_amount)} ₽</div>
            </div>
            <div className="kpi ok">
              <div className="label">Закрыто актами</div>
              <div className="value">{money(t.closed_amount)}</div>
              <div className="sub">{t.closed_count} шт.</div>
            </div>
            <div className="kpi">
              <div className="label">Не закрыто</div>
              <div className="value">{money(t.open_amount)}</div>
              <div className="sub">
                {t.not_sent_count} без акта · {t.awaiting_count} ждут подписи
              </div>
            </div>
            <div className="kpi danger">
              <div className="label">Просрочено</div>
              <div className="value">{money(t.needs_attention_amount)}</div>
              <div className="sub">{t.needs_attention_count} требуют внимания</div>
            </div>
            <div className="kpi">
              <div className="label">Проектов</div>
              <div className="value">{t.projects_count}</div>
              <div className="sub">{payments.filter((p) => !p.project_id).length} оплат без привязки</div>
            </div>
          </div>
        )}

        <div className="card">
          <div className="filters">
            <div>
              <label htmlFor="f-search">Поиск</label>
              <input
                id="f-search"
                placeholder="назначение или клиент"
                value={filters.search || ""}
                onChange={(e) => set("search", e.target.value)}
                style={{ minWidth: 200 }}
              />
            </div>
            <div>
              <label htmlFor="f-client">Клиент</label>
              <select id="f-client" value={filters.client_id ?? ""} onChange={(e) => set("client_id", e.target.value ? Number(e.target.value) : "")}>
                <option value="">Все</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="f-project">Проект</label>
              <select id="f-project" value={filters.project_id ?? ""} onChange={(e) => set("project_id", e.target.value ? Number(e.target.value) : "")}>
                <option value="">Все</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="f-stage">Этап / услуга</label>
              <select id="f-stage" value={filters.service_stage || ""} onChange={(e) => set("service_stage", e.target.value)}>
                <option value="">Все</option>
                {services.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="f-status">Статус акта</label>
              <select id="f-status" value={filters.act_status || ""} onChange={(e) => set("act_status", e.target.value)}>
                <option value="">Все</option>
                {Object.entries(STATUS_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="f-from">Дата с</label>
              <input id="f-from" type="date" value={filters.date_from || ""} onChange={(e) => set("date_from", e.target.value)} />
            </div>
            <div>
              <label htmlFor="f-to">Дата по</label>
              <input id="f-to" type="date" value={filters.date_to || ""} onChange={(e) => set("date_to", e.target.value)} />
            </div>
            <div>
              <label>
                <input
                  type="checkbox"
                  checked={!!filters.unbound_only}
                  onChange={(e) => set("unbound_only", e.target.checked)}
                />{" "}
                только без проекта
              </label>
            </div>
            <button onClick={() => setFilters({ as_of: DEMO_AS_OF })}>Сбросить</button>
            <a href={api.exportUrl(filters)} download>
              <button type="button">Экспорт CSV</button>
            </a>
          </div>
        </div>

        <div className="tabs">
          <button className={tab === "payments" ? "active" : ""} onClick={() => setTab("payments")}>
            Оплаты и акты ({payments.length})
          </button>
          <button className={tab === "projects" ? "active" : ""} onClick={() => setTab("projects")}>
            Сводка по проектам
          </button>
        </div>

        {busy && <p className="muted">Загрузка…</p>}

        {tab === "payments" ? (
          <PaymentsTable
            payments={payments}
            projects={projects}
            asOf={filters.as_of}
            statusLabel={STATUS_LABEL}
            onChanged={load}
            onError={setError}
          />
        ) : (
          <ProjectsSummary
            rows={dashboard?.by_project || []}
            projects={projects}
            onChanged={load}
            onError={setError}
          />
        )}
      </main>
    </>
  );
}
