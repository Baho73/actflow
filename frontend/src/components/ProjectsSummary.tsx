// FILE: frontend/src/components/ProjectsSummary.tsx
// VERSION: 1.0.0
// START_MODULE_CONTRACT
//   PURPOSE: Сводка по проектам и юрлицам: сколько оплачено, сколько актов закрыто, % закрытия.
//   SCOPE: Отображение агрегатов сервера + переименование проектов-черновиков.
//   LAYER: UI
//   DEPENDS: M-API
//   LINKS: M-UI, UC-007
// END_MODULE_CONTRACT
//
// START_MODULE_MAP
//   default - ProjectsSummary
// END_MODULE_MAP
//
// START_CHANGE_SUMMARY
//   LAST_CHANGE: [v1.0.0 - Initial implementation]
// END_CHANGE_SUMMARY

import { useState } from "react";
import { Project, ProjectSummary, api } from "../api";

function money(v: string): string {
  return Number(v).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function ProjectsSummary({
  rows,
  projects,
  onChanged,
  onError,
}: {
  rows: ProjectSummary[];
  projects: Project[];
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [name, setName] = useState("");

  const byId = new Map(projects.map((p) => [p.id, p]));

  async function rename(id: number) {
    try {
      await api.renameProject(id, name);
      setEditing(null);
      onChanged();
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!rows.length) return <div className="card empty">Данных нет.</div>;

  return (
    <div className="card">
      <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
        Проекты, созданные автоматически по номеру договора, помечены. Переименуйте их — система
        не выдаёт догадку за факт.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Проект</th>
              <th>Клиент</th>
              <th>Договор</th>
              <th className="num">Оплат</th>
              <th className="num">Получено</th>
              <th className="num">Актов отправлено</th>
              <th className="num">Подписано</th>
              <th>Закрытие</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const project = r.project_id ? byId.get(r.project_id) : undefined;
              const ratio = r.closed_ratio ? Number(r.closed_ratio) : 0;
              return (
                <tr key={r.project_id ?? "none"}>
                  <td>
                    {editing === r.project_id ? (
                      <span className="row">
                        <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
                        <button className="primary" onClick={() => rename(r.project_id!)}>ОК</button>
                        <button onClick={() => setEditing(null)}>Отмена</button>
                      </span>
                    ) : (
                      <>
                        <b>{r.project_name}</b>
                        {project?.auto_created && (
                          <span className="chip warn" style={{ marginLeft: 6 }}>черновик</span>
                        )}
                        {r.project_id && (
                          <button
                            style={{ marginLeft: 6, padding: "1px 6px", fontSize: 12 }}
                            onClick={() => {
                              setEditing(r.project_id!);
                              setName(r.project_name);
                            }}
                          >
                            ✎
                          </button>
                        )}
                      </>
                    )}
                  </td>
                  <td>{project?.client_name || "—"}</td>
                  <td className="muted">{project?.contract_number || "—"}</td>
                  <td className="num">{r.payments_count}</td>
                  <td className="num money">{money(r.total)}</td>
                  <td className="num">{r.sent_count}</td>
                  <td className="num">{r.signed_count}</td>
                  <td>
                    <div className="row">
                      <div className="bar" style={{ flex: 1 }}>
                        <span style={{ width: `${Math.round(ratio * 100)}%` }} />
                      </div>
                      <span className="muted" style={{ fontSize: 12, minWidth: 34 }}>
                        {Math.round(ratio * 100)}%
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
