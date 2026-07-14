// FILE: frontend/src/components/ImportPanel.tsx
// VERSION: 1.0.0
// START_MODULE_CONTRACT
//   PURPOSE: Загрузка выписки и честный отчёт: принято / уже было / отсеяно с причинами.
//   SCOPE: Отображение отчёта. Молчаливого выбрасывания операций нет — всё показано.
//   LAYER: UI
//   DEPENDS: M-API
//   LINKS: M-UI, DF-IMPORT
// END_MODULE_CONTRACT
//
// START_MODULE_MAP
//   default - ImportPanel
// END_MODULE_MAP
//
// START_CHANGE_SUMMARY
//   LAST_CHANGE: [v1.0.0 - Initial implementation]
// END_CHANGE_SUMMARY

import { useRef, useState } from "react";
import { ImportReport, api } from "../api";

function money(v: string): string {
  return Number(v).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function ImportPanel({
  onImported,
  report,
  onError,
}: {
  onImported: (r: ImportReport) => void;
  report: ImportReport | null;
  onError: (msg: string) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      onError("Выберите PDF-файл выписки");
      return;
    }
    setBusy(true);
    try {
      onImported(await api.importStatement(file));
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Импорт банковской выписки</h2>
      <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
        Из выписки берутся только оплаты клиентов. Налоги, комиссии банка, переводы между
        своими счетами и зарплата в дашборд не попадают — но вы увидите их в отчёте с причиной.
      </p>
      <div className="row">
        <input ref={fileRef} type="file" accept="application/pdf,.pdf" />
        <button className="primary" onClick={upload} disabled={busy}>
          {busy ? "Разбираем…" : "Загрузить выписку"}
        </button>
      </div>

      {report && (
        <div style={{ marginTop: 14 }}>
          <div className="banner ok">
            Принято оплат: <b>{report.imported}</b>
            {report.already_known > 0 && <> · уже было: <b>{report.already_known}</b></>}
            {report.created_projects > 0 && <> · создано проектов: <b>{report.created_projects}</b></>}
            {report.unbound > 0 && <> · требуют привязки: <b>{report.unbound}</b></>}
          </div>

          {report.skipped.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Не пошло в дашборд</th>
                    <th className="num">Операций</th>
                    <th className="num">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  {report.skipped.map((g) => (
                    <tr key={g.code}>
                      <td>{g.text}</td>
                      <td className="num">{g.count}</td>
                      <td className="num money">{money(g.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
