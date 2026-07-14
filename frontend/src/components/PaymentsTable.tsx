// FILE: frontend/src/components/PaymentsTable.tsx
// VERSION: 1.0.0
// START_MODULE_CONTRACT
//   PURPOSE: Таблица оплат: статус акта, способ привязки, отметки, массовые действия.
//   SCOPE: Отображение и команды. Статус приходит с сервера — здесь не вычисляется.
//   LAYER: UI
//   DEPENDS: M-API
//   LINKS: M-UI
// END_MODULE_CONTRACT
//
// START_MODULE_MAP
//   default - PaymentsTable
// END_MODULE_MAP
//
// START_CHANGE_SUMMARY
//   LAST_CHANGE: [v1.0.0 - Initial implementation]
// END_CHANGE_SUMMARY

import { useState } from "react";
import { ActStatus, Payment, Project, api } from "../api";

const BINDING_LABEL: Record<string, string> = {
  by_contract: "по договору",
  by_client_service: "по клиенту и услуге",
  manual: "вручную",
  unbound: "требует привязки",
};

function money(v: string): string {
  return Number(v).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function PaymentsTable({
  payments,
  projects,
  asOf,
  statusLabel,
  onChanged,
  onError,
}: {
  payments: Payment[];
  projects: Project[];
  asOf?: string;
  statusLabel: Record<ActStatus, string>;
  onChanged: () => void;
  onError: (msg: string) => void;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  const toggle = (id: number) =>
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const allSelected = payments.length > 0 && selected.size === payments.length;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      onChanged();
      setSelected(new Set());
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!payments.length) {
    return <div className="card empty">Оплат нет. Загрузите банковскую выписку выше.</div>;
  }

  return (
    <div className="card">
      {/* массовые действия применяются к отмеченным строкам текущего фильтра */}
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="muted">Выбрано: {selected.size}</span>
        <button
          disabled={!selected.size || busy}
          onClick={() => run(() => api.bulkAct([...selected], { is_sent: true }, asOf))}
        >
          Отметить акты отправленными
        </button>
        <button
          disabled={!selected.size || busy}
          onClick={() => run(() => api.bulkAct([...selected], { is_signed: true }, asOf))}
        >
          Отметить подписанными
        </button>
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th style={{ width: 28 }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => setSelected(e.target.checked ? new Set(payments.map((p) => p.id)) : new Set())}
                  aria-label="Выбрать все"
                />
              </th>
              <th>Дата</th>
              <th>Клиент / ИНН</th>
              <th>Проект</th>
              <th>Этап</th>
              <th>Счёт / договор</th>
              <th className="num">Сумма</th>
              <th>Акт</th>
              <th>Статус</th>
              <th>Назначение</th>
            </tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.has(p.id)}
                    onChange={() => toggle(p.id)}
                    aria-label={`Выбрать оплату ${p.id}`}
                  />
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {new Date(p.payment_date).toLocaleDateString("ru-RU")}
                </td>
                <td>
                  <div>{p.client_name}</div>
                  <div className="muted" style={{ fontSize: 11 }}>{p.client_inn}</div>
                </td>
                <td>
                  {/* привязка проекта: менеджер видит СПОСОБ и может поправить */}
                  <select
                    value={p.project_id ?? ""}
                    onChange={(e) =>
                      run(() => api.bindProject(p.id, e.target.value ? Number(e.target.value) : null, asOf))
                    }
                    style={{ maxWidth: 180 }}
                  >
                    <option value="">— требует привязки —</option>
                    {projects.map((pr) => (
                      <option key={pr.id} value={pr.id}>{pr.name}</option>
                    ))}
                  </select>
                  <div className={`binding ${p.binding_method}`}>
                    {BINDING_LABEL[p.binding_method]}
                    {p.stage_mismatch && <span className="chip warn" style={{ marginLeft: 4 }}>услуга не совпала</span>}
                  </div>
                  {p.conflict_reason && (
                    <div className="binding unbound" title={p.conflict_reason}>
                      {p.conflict_reason}
                    </div>
                  )}
                </td>
                <td>
                  {p.service_stages.length
                    ? p.service_stages.map((s) => <span className="chip" key={s}>{s}</span>)
                    : <span className="muted">не определён</span>}
                </td>
                <td className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                  {p.invoice_numbers.length ? `сч. ${p.invoice_numbers.join(", ")}` : "—"}
                  {p.contract_number && <div>дог. {p.contract_number}</div>}
                </td>
                <td className="num money">{money(p.amount)}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <label style={{ display: "block", fontSize: 12 }}>
                    <input
                      type="checkbox"
                      checked={p.is_sent}
                      disabled={busy}
                      onChange={(e) => run(() => api.patchAct(p.id, { is_sent: e.target.checked }, asOf))}
                    />{" "}
                    отправлен
                  </label>
                  <label style={{ display: "block", fontSize: 12 }}>
                    <input
                      type="checkbox"
                      checked={p.is_signed}
                      disabled={busy}
                      onChange={(e) => run(() => api.patchAct(p.id, { is_signed: e.target.checked }, asOf))}
                    />{" "}
                    подписан
                  </label>
                </td>
                <td>
                  <span className={`status ${p.act_status}`}>{statusLabel[p.act_status]}</span>
                </td>
                <td className="purpose" title={p.purpose_text}>{p.purpose_text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
