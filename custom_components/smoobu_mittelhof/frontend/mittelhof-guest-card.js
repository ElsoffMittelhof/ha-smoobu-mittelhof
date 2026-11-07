/* Admin-only guest conversation and editable invoice/message DRAFT card.
 * This card never issues an invoice and never sends automatically.
 */
class MittelhofGuestCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._inbox = null;
    this._selected = null;
    this._busy = false;
    this._error = "";
    this._hasUnsaved = false;
  }

  setConfig(config) {
    this._config = config || {};
  }

  set hass(value) {
    this._hass = value;
    if (!this._loaded) {
      this._loaded = true;
      this._loadInbox();
    }
  }

  getCardSize() { return 8; }

  static esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async _api(method, route, data) {
    return this._hass.callApi(method, "smoobu_mittelhof/guest/v1/" + route, data);
  }

  async _run(callback) {
    if (this._busy) return;
    this._busy = true;
    this._error = "";
    try { await callback(); }
    catch (err) { this._error = String(err?.message || err); }
    finally {
      this._busy = false;
      if (this._hasUnsaved && this._error) {
        // Never destroy unsaved invoice or message fields after a failed API save.
        window.alert("Änderungen NICHT gespeichert: " + this._error);
      } else {
        this._render();
      }
    }
  }

  async _loadInbox() {
    if (this._hasUnsaved && !window.confirm("Ungespeicherte Änderungen verwerfen?")) return;
    await this._run(async () => { this._inbox = await this._api("GET", "threads"); });
  }

  async _open(id) {
    if (this._hasUnsaved && !window.confirm("Ungespeicherte Änderungen verwerfen?")) return;
    await this._run(async () => {
      this._hasUnsaved = false;
      this._selected = await this._api("GET", "bookings/" + encodeURIComponent(id));
    });
  }

  async _prepare() {
    if (!this._selected) return;
    if (this._hasUnsaved && !window.confirm("Ungespeicherte Änderungen verwerfen?")) return;
    if (this._selected.source_changed && !window.confirm(
      "Smoobu hat Buchungsdaten geändert (aktueller Buchungsbetrag: " +
      this._selected.booking.price +
      " €). Die vorhandenen Rechnungspositionen werden NICHT überschrieben. " +
      "Bitte die Entwurfsbeträge anschließend selbst kontrollieren."
    )) return;
    await this._run(async () => {
      this._hasUnsaved = false;
      const id = this._selected.booking.id;
      await this._api("POST", "bookings/" + id + "/draft", {});
      this._selected = await this._api("GET", "bookings/" + id);
      await this._refreshInboxSilent();
    });
  }

  async _refreshInboxSilent() {
    this._inbox = await this._api("GET", "threads");
  }

  _field(key, label, value, multiline = false) {
    const esc = MittelhofGuestCard.esc;
    return '<label><span>' + esc(label) + '</span>' +
      (multiline
        ? '<textarea data-field="' + esc(key) + '" rows="3">' + esc(value) + '</textarea>'
        : '<input data-field="' + esc(key) + '" value="' + esc(value) + '" />') +
      '</label>';
  }

  _collectInvoice() {
    const root = this.shadowRoot;
    const values = {};
    const keys = [
      "recipient_name", "recipient_address", "description", "total_gross",
      "paid_amount", "due_date", "payment_note", "tax_note"
    ];
    for (const key of keys) {
      const el = root.querySelector('[data-field="' + key + '"]');
      if (el) values[key] = el.value;
    }
    values.payment_flow = root.querySelector('[data-field="payment_flow"]').value;
    values.payment_verified = root.querySelector('[data-field="payment_verified"]').checked;
    values.line_items = JSON.parse(root.querySelector('[data-field="line_items"]').value);
    return values;
  }

  async _save() {
    const d = this._selected?.draft;
    if (!d) return;
    let changes;
    try {
      changes = {
        invoice: this._collectInvoice(),
        message: {
          subject: this.shadowRoot.querySelector('[data-field="subject"]').value,
          body: this.shadowRoot.querySelector('[data-field="body"]').value
        }
      };
    } catch (err) {
      this._error = "Rechnungspositionen sind kein gültiges JSON: " + String(err.message || err);
      window.alert("Änderungen NICHT gespeichert: " + this._error);
      return;
    }
    await this._run(async () => {
      const id = this._selected.booking.id;
      await this._api("PATCH", "bookings/" + id + "/draft", {
        revision: d.revision, changes
      });
      this._selected = await this._api("GET", "bookings/" + id);
      this._hasUnsaved = false;
      await this._refreshInboxSilent();
    });
  }

  async _action(action) {
    const d = this._selected?.draft;
    if (!d || this._hasUnsaved) return;
    if (action === "regenerate" && !window.confirm(
      "Die Nachricht aus den gespeicherten Zahlungsdaten neu erzeugen? Ein bisheriger Nachrichtentext wird ersetzt."
    )) return;
    if (action === "send" && !window.confirm(
      "Die freigegebene Nachricht jetzt wirklich über Smoobu an den Gast senden? " +
      "Ein Rechnungs-PDF wird NICHT angehängt."
    )) return;
    await this._run(async () => {
      const id = this._selected.booking.id;
      await this._api("POST", "bookings/" + id + "/" + action, { revision: d.revision });
      this._selected = await this._api("GET", "bookings/" + id);
      await this._refreshInboxSilent();
    });
  }

  _renderInbox() {
    const esc = MittelhofGuestCard.esc;
    if (!this._inbox) return '<p>Posteingang wird geladen …</p>';
    const threads = this._inbox.threads || [];
    const drafts = this._inbox.drafts || [];
    const seen = new Set();
    const rows = threads.map((t) => {
      const id = String(t.booking?.id || "");
      if (!/^\d+$/.test(id)) return "";
      seen.add(id);
      return '<button class="thread" data-booking="' + esc(id) + '">' +
        '<strong>' + esc(t.apartment?.name || "Unterkunft") + '</strong>' +
        '<span>' + esc(t.booking?.guest_name || "Gast") + '</span>' +
        '<small>' + esc(t.latest_message?.text_content || "Nachricht") + '</small>' +
        '</button>';
    }).join("");
    const other = drafts.filter((d) => !seen.has(String(d.booking_id))).map((d) =>
      '<button class="thread" data-booking="' + esc(d.booking_id) + '">' +
      '<strong>Entwurf · Buchung #' + esc(d.booking_id) + '</strong>' +
      '<span>' + esc(d.channel || "") + '</span>' +
      '<small>Nachricht: ' + esc(d.message_status) + ' · Rechnung: ' + esc(d.invoice_status) + '</small>' +
      '</button>'
    ).join("");
    return '<h3>Posteingang · ' + esc(this._inbox.unread_messages || 0) + ' ungelesen</h3>' +
      '<div class="thread-list">' + (rows + other || '<p>Keine Konversationen/Entwürfe vorhanden</p>') + '</div>' +
      '<small>Die Posteingangsliste zeigt die erste Smoobu-Seite (bis 100 Gespräche) und alle lokalen Entwürfe.</small>';
  }

  _renderBooking() {
    const esc = MittelhofGuestCard.esc;
    const selected = this._selected;
    if (!selected) return '<div class="empty">Links eine Buchung auswählen.</div>';
    const b = selected.booking;
    const d = selected.draft;
    const messages = (selected.messages || []).map((m) =>
      '<div class="bubble ' + (Number(m.type) === 1 ? "incoming" : "outgoing") + '">' +
      '<small>' + (Number(m.type) === 1 ? 'Gast' : 'Gastgeber') + ' · ' + esc(m.subject || '') + '</small>' +
      '<div class="body">' + esc(m.message || m.htmlMessage || m.messageHtml || '').replace(/&lt;br\s*\/?&gt;/gi, '\n') + '</div></div>'
    ).join("");
    let html = '<h3>' + esc(b.house) + ' · ' + esc(b.guest) + '</h3>' +
      '<p class="meta">Buchung #' + esc(b.id) + ' · ' + esc(b.arrival) + ' – ' + esc(b.departure) +
      ' · ' + esc(b.channel?.name || b.channel || '') + '</p>' +
      '<div class="history"><h4>Gesprächsverlauf</h4>' + (messages || '<p>Keine Nachrichten</p>') + '</div>';
    if (!d) return html + '<button data-op="prepare">Entwurf für Buchung vorbereiten</button>';
    const inv = d.invoice, msg = d.message;
    html += '<p class="meta">Entwurf Revision ' + esc(d.revision) + ' · Nachricht: ' +
      esc(msg.status) + ' · Rechnung: ' + esc(inv.status) + '</p>';
    const pf = selected.invoice_preflight;
    if (pf) {
      html += '<div class="preflight"><h4>Rechnungsprüfung (Entwurf)</h4>' +
        '<p>Brutto: ' + esc(pf.gross) + ' € · Bezahlt: ' + esc(pf.paid) +
        ' € · Offen: ' + esc(pf.outstanding) + ' € · Positionssumme: ' +
        esc(pf.line_total) + ' €</p>' +
        (pf.errors || []).map((e) => '<p class="warning">Fehler: ' + esc(e) + '</p>').join('') +
        (pf.warnings || []).map((e) => '<p class="warning">Prüfen: ' + esc(e) + '</p>').join('') +
        '<p><strong>Keine Rechnungsfreigabe und kein ZUGFeRD-Versand in V1.</strong></p></div>';
    }
    if (selected.source_changed) html += '<div class="warning">Buchung seit Entwurf verändert. Bitte erneut vorbereiten und prüfen.</div>';
    if (!this._inbox?.message_send_enabled) html += '<p class="warning">Echter Gastversand ist in den HA-Integrationsoptionen deaktiviert.</p>';
    html += '<div class="edit-grid"><section><h4>Rechnungsentwurf (noch keine Rechnung)</h4>' +
      '<p><img class="logo" src="/local/smoobu_mittelhof/invoice-logo.png" alt="Ferienhaus Mittelhof – Logo" /></p>' +
      this._field("recipient_name", "Rechnungsempfänger", inv.recipient_name) +
      this._field("recipient_address", "Rechnungsanschrift", inv.recipient_address, true) +
      this._field("description", "Leistungstext", inv.description, true) +
      this._field("total_gross", "Rechnungsbetrag brutto (€)", inv.total_gross) +
      this._field("paid_amount", "Nachweislich bereits bezahlt (€)", inv.paid_amount) +
      this._field("due_date", "Zahlungsziel (JJJJ-MM-TT)", inv.due_date) +
      '<label><span>Zahlungsweg</span><select data-field="payment_flow">' +
      [["unverified","Ungeklärt"],["platform","Plattform"],["guest_invoice","Rechnung/Überweisung"],["already_paid","Bereits bezahlt"]].map(([value,label]) =>
        '<option value="' + value + '"' + (inv.payment_flow === value ? " selected" : "") + '>' + label + '</option>'
      ).join("") + '</select></label>' +
      '<label class="checkbox"><input type="checkbox" data-field="payment_verified"' +
      (inv.payment_verified ? ' checked' : '') + ' /> Zahlung manuell geprüft</label>' +
      this._field("payment_note", "Zahlungshinweis", inv.payment_note, true) +
      this._field("tax_note", "Steuerhinweis (fachlich prüfen)", inv.tax_note, true) +
      this._field("line_items", "Positionen als JSON (inkl. steuerlicher Einordnung)", JSON.stringify(inv.line_items, null, 2), true) +
      '<p class="warning">Keine Steuerberechnung, Rechnungsnummer oder ZUGFeRD-Datei in diesem Entwicklungsstand.</p>' +
      '</section><section><h4>Nachrichtenentwurf</h4>' +
      this._field("subject", "Betreff", msg.subject) +
      this._field("body", "Nachricht", msg.body, true) +
      '<p>Die Nachricht wird über Smoobu als Text gesendet. Es wird kein Rechnungsanhang mitgeschickt.</p>' +
      '</section></div><div class="actions">' +
      '<button data-op="prepare">Mit aktuellem Buchungsstand abgleichen</button>' +
      '<button data-op="save">Änderungen speichern</button>' +
      '<button data-op="regenerate" ' +
      (msg.status === "draft" && !selected.source_changed ? "" : "disabled") +
      '>Nachricht aus Zahlungsdaten erzeugen</button>' +
      '<button data-op="approve" ' + (msg.status === "draft" && !selected.source_changed ? "" : "disabled") +
      '>Nachricht freigeben</button>' +
      '<button class="send" data-op="send" ' + (msg.status === "approved" && !selected.source_changed && this._inbox?.message_send_enabled ? "" : "disabled") +
      '>Freigegebene Nachricht senden</button>' +
      '</div>';
    return html;
  }

  _render() {
    const esc = MittelhofGuestCard.esc;
    this.shadowRoot.innerHTML = '<style>' +
      ':host{display:block;color:var(--primary-text-color)}ha-card{display:block;padding:16px;max-width:1480px;margin:auto}' +
      '.layout{display:grid;grid-template-columns:minmax(230px,310px) minmax(0,1fr);gap:18px}.thread-list{max-height:65vh;overflow:auto}' +
      '.thread{display:flex;flex-direction:column;text-align:left;width:100%;margin:5px 0;border-radius:8px;padding:10px;border:1px solid var(--divider-color);background:var(--card-background-color);cursor:pointer}' +
      '.thread small,.meta{color:var(--secondary-text-color)}.thread small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '.history{max-height:330px;overflow:auto;padding:8px;border:1px solid var(--divider-color);border-radius:8px;margin-bottom:15px}' +
      '.bubble{padding:10px;border-radius:8px;margin:5px 0;white-space:pre-wrap;background:var(--secondary-background-color)}' +
      '.bubble.outgoing{margin-left:12%}.bubble.incoming{margin-right:12%}.body{white-space:pre-wrap;overflow-wrap:anywhere}' +
      '.edit-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}label{display:flex;flex-direction:column;gap:3px;margin:10px 0;font-size:13px}' +
      'input,textarea,select{box-sizing:border-box;width:100%;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);padding:8px;border-radius:6px;font:inherit}' +
      'textarea{min-height:80px}.checkbox{flex-direction:row;align-items:center}.checkbox input{width:auto}' +
      'button{cursor:pointer;border:1px solid var(--divider-color);border-radius:7px;padding:9px;background:var(--secondary-background-color);color:var(--primary-text-color)}' +
      'button:disabled{opacity:.45;cursor:not-allowed}.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.send{border-color:var(--success-color,#2a8)}' +
      '.preflight{border:1px solid var(--divider-color);padding:10px;border-radius:8px;margin:10px 0}.warning{border-left:3px solid #c9943c;padding:8px;color:var(--primary-text-color)}.logo{max-width:220px;max-height:90px;object-fit:contain}' +
      '@media(max-width:850px){.layout,.edit-grid{grid-template-columns:1fr}.thread-list{max-height:240px}}' +
      '</style><ha-card><header><h2>Gäste & Rechnungsentwürfe</h2>' +
      '<button data-op="refresh" ' + (this._busy ? "disabled" : "") + '>Aktualisieren</button></header>' +
      (this._error ? '<p class="warning" role="alert">' + esc(this._error) + '</p>' : '') +
      '<div class="layout"><aside>' + this._renderInbox() + '</aside><main>' +
      this._renderBooking() + '</main></div></ha-card>';
    this.shadowRoot.querySelectorAll('[data-field]').forEach((el) =>
      el.addEventListener("input", () => {
        this._hasUnsaved = true;
        for (const op of ["regenerate", "approve", "send"]) {
          const button = this.shadowRoot.querySelector('[data-op="' + op + '"]');
          if (button) button.disabled = true;
        }
      }));
    const logo = this.shadowRoot.querySelector('.logo');
    if (logo) logo.addEventListener("error", () => { logo.style.display = "none"; });
    this.shadowRoot.querySelectorAll('[data-booking]').forEach((el) =>
      el.addEventListener("click", () => this._open(el.dataset.booking)));
    this.shadowRoot.querySelectorAll('[data-op]').forEach((el) =>
      el.addEventListener("click", () => {
        const actions = { refresh: () => this._loadInbox(), prepare: () => this._prepare(),
          save: () => this._save(), regenerate: () => this._action("regenerate"),
          approve: () => this._action("approve"), send: () => this._action("send") };
        if (actions[el.dataset.op]) actions[el.dataset.op]();
      }));
  }
}

if (!customElements.get("mittelhof-guest-card")) {
  customElements.define("mittelhof-guest-card", MittelhofGuestCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "mittelhof-guest-card")) {
  window.customCards.push({
    type: "mittelhof-guest-card",
    name: "Mittelhof Gäste & Rechnungsentwürfe",
    description: "Administrator-Posteingang und manuell freizugebende Entwürfe"
  });
}
