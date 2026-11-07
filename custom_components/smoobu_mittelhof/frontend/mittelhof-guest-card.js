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
      await this._syncInvoiceService();
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

  _positionRow(item = {}) {
    const esc = MittelhofGuestCard.esc;
    const names = [
      ["rent", "Miete"], ["cleaning", "Reinigung"],
      ["extra_person", "Zusätzliche Person"], ["dog", "Hund"],
      ["stay_discount", "Nachlass nach Mietdauer"]
    ];
    const kind = item.position_type || "";
    const pick = names.map(([key, name]) =>
      '<option value="' + key + '"' + (kind === key ? ' selected' : '') +
      '>' + name + '</option>').join("");
    return '<div class="position-row" data-position-row>' +
      '<label>Art der Leistung<select data-field="position_type">' +
      '<option value="">Bitte auswählen</option>' + pick + '</select></label>' +
      '<label>Beschreibung<input data-field="description" value="' +
      esc(item.description || "") + '"></label>' +
      '<label>Menge (Person/Hund max. 2)<input type="number" min="1" max="2" step="1" ' +
      'data-field="quantity" value="' + esc(item.quantity ?? 1) + '"></label>' +
      '<label>Brutto für diese Position (€)<input data-field="gross" ' +
      'inputmode="decimal" value="' + esc(item.gross ?? "0.00") + '"></label>' +
      '<label>Umsatzsteuer<input value="7 % (Mittelhof-Leistung)" disabled></label>' +
      '<label>Bei Nachlass: bestätigte Rabattstaffel<input data-field="discount_rule" ' +
      'placeholder="Automatisch: 10 % ab 8 Nächten" value="' +
      esc(item.discount_rule || "") + '"></label>' +
      '<label>Bei Nachlass: Anzahl Übernachtungen<input data-field="discount_nights" ' +
      'type="number" min="1" max="365" step="1" value="' +
      esc(item.discount_nights ?? "") + '"></label>' +
      '<button type="button" data-remove-position>Position entfernen</button>' +
      '</div>';
  }

  _positionEditor(invoice) {
    const rows = (invoice.line_items || []).map((item) => this._positionRow(item)).join("");
    return '<h4>Rechnungspositionen (alle 7 %)</h4>' +
      '<p class="meta">Automatisch: ab 8 Übernachtungen 10 % auf die gesamte Miete ' +
      '(nicht auf Reinigung, Person oder Hund). Bei 1–7 Nächten kein Nachlass. ' +
      'Beim Speichern wird der Rabatt serverseitig neu berechnet und als eigene ' +
      'negative Position ausgewiesen. Brutto je Zeile ist der Preis für die Menge.</p>' +
      '<div data-position-list>' + rows + '</div>' +
      '<button type="button" data-add-position>Position hinzufügen</button>' +
      '<button type="button" data-use-position-total>Positionssumme übernehmen</button>' +
      '<p class="meta" data-position-total>Rabatt und Positionssumme werden beim Speichern automatisch berechnet.</p>';
  }

  _collectLines() {
    const rows = Array.from(this.shadowRoot.querySelectorAll('[data-position-row]'));
    return rows.map((row) => {
      const v = (name) => row.querySelector('[data-field="' + name + '"]').value;
      const kind = v("position_type");
      const qty = Number(v("quantity"));
      if (!Number.isSafeInteger(qty)) throw new Error("Menge muss ganzzahlig sein");
      const line = {
        position_type: kind, description: v("description"),
        quantity: qty, gross: v("gross").replace(",", "."), tax_rate: "7"
      };
      if (kind === "stay_discount") {
        const nights = Number(v("discount_nights"));
        if (!Number.isSafeInteger(nights) || nights < 1)
          throw new Error("Für den Mietdauernachlass bitte die Nächte angeben");
        line.discount_nights = nights;
        line.discount_rule = v("discount_rule");
      }
      return line;
    });
  }

  _rentalNights() {
    const b = this._selected?.booking || {};
    const arrival = Date.parse(String(b.arrival || "") + "T00:00:00Z");
    const departure = Date.parse(String(b.departure || "") + "T00:00:00Z");
    const nights = Math.round((departure - arrival) / 86400000);
    if (!Number.isSafeInteger(nights) || nights < 1 || nights > 365)
      throw new Error("Gültige An- und Abreise für den Mietdauernachlass fehlen");
    return nights;
  }

  _positionSumCents() {
    const rows = this._collectLines();
    const cents = (value) => {
      value = String(value).trim();
      if (!/^-?\d+(?:\.\d{1,2})?$/.test(value))
        throw new Error("Jede Position braucht einen centgenauen Bruttobetrag");
      const minus = value.startsWith("-") ? -1n : 1n;
      const parts = value.replace("-", "").split(".");
      return minus * (BigInt(parts[0]) * 100n +
        BigInt((parts[1] || "").padEnd(2, "0")));
    };
    const rents = rows.filter((row) => row.position_type === "rent");
    if (rents.length !== 1) {
      return rows.reduce((sum, row) => sum + cents(row.gross), 0n);
    }
    const nights = this._rentalNights();
    const rentCents = cents(rents[0].gross);
    if (rentCents <= 0n) throw new Error("Mietbetrag muss positiv sein");
    const discount = nights >= 8 ? (rentCents + 5n) / 10n : 0n;
    if (nights >= 8 && discount === 0n) throw new Error("Miete zu klein für 10 % Rabatt");
    return rows.filter((row) => row.position_type !== "stay_discount")
      .reduce((sum, row) => sum + cents(row.gross), 0n) - discount;
  }

  _positionSumText() {
    const cents = this._positionSumCents();
    const magnitude = cents < 0n ? -cents : cents;
    return (cents < 0n ? "-" : "") +
      String(magnitude / 100n) + "." +
      String(magnitude % 100n).padStart(2, "0");
  }

  _markUnsaved() {
    this._hasUnsaved = true;
    for (const op of ["regenerate", "approve", "send", "preview-request",
      "invoice-export", "demo-build", "demo-verify", "demo-approve",
      "demo-archive", "demo-correction", "demo-download"]) {
      const button = this.shadowRoot.querySelector('[data-op="' + op + '"]');
      if (button) button.disabled = true;
    }
  }

  _addPosition() {
    const list = this.shadowRoot.querySelector('[data-position-list]');
    if (!list || list.children.length >= 20) {
      window.alert("Maximal 20 Rechnungspositionen zulässig");
      return;
    }
    const kind = window.prompt(
      "Position hinzufügen: rent (Miete), cleaning (Reinigung), " +
      "extra_person (Zusätzliche Person), dog (Hund). Der Nachlass entsteht automatisch."
    );
    const labels = {
      rent: "Miete", cleaning: "Reinigung",
      extra_person: "Zusätzliche Person", dog: "Hund",
      stay_discount: "Nachlass aufgrund der Mietdauer"
    };
    if (kind === null) return;
    const type = kind.trim().toLowerCase();
    if (!labels[type]) {
      window.alert("Bitte einen der fünf angegebenen Positionstypen eingeben");
      return;
    }
    const arrival = Date.parse(this._selected?.booking?.arrival || "");
    const departure = Date.parse(this._selected?.booking?.departure || "");
    const nights = Number.isFinite(arrival) && Number.isFinite(departure) ?
      Math.round((departure - arrival) / 86400000) : 0;
    const row = {
      position_type: type, description: labels[type], quantity: 1,
      gross: type === "stay_discount" ? "-0.01" : "0.00",
      discount_nights: type === "stay_discount" && nights > 0 ? nights : "",
      discount_rule: ""
    };
    list.insertAdjacentHTML("beforeend", this._positionRow(row));
    const added = list.lastElementChild;
    added.querySelectorAll('[data-field]').forEach((el) =>
      el.addEventListener("input", () => this._markUnsaved()));
    added.querySelector('[data-remove-position]').addEventListener("click",
      () => { added.remove(); this._markUnsaved(); });
    this._markUnsaved();
  }

  _collectInvoice() {
    const root = this.shadowRoot;
    const values = {};
    const keys = [
      "recipient_name", "recipient_address", "recipient_street",
      "recipient_postal_code", "recipient_city", "recipient_country", "description", "total_gross",
      "paid_amount", "due_date", "payment_note", "tax_note"
    ];
    for (const key of keys) {
      const el = root.querySelector('[data-field="' + key + '"]');
      if (el) values[key] = el.value;
    }
    values.payment_flow = root.querySelector('[data-field="payment_flow"]').value;
    values.payment_verified = root.querySelector('[data-field="payment_verified"]').checked;
    values.line_items = this._collectLines();
    return values;
  }

  async _save() {
    const d = this._selected?.draft;
    if (!d) return;
    let changes;
    try {
      changes = {invoice: this._collectInvoice()};
      // A delivered guest message is immutable. Never send a message patch
      // when only accounting fields are being edited after delivery.
      if (!["sent", "sending", "delivery_unknown"].includes(d.message.status)) {
        changes.message = {
          subject: this.shadowRoot.querySelector('[data-field="subject"]').value,
          body: this.shadowRoot.querySelector('[data-field="body"]').value
        };
      }
    } catch (err) {
      this._error = "Rechnungspositionen prüfen: " + String(err.message || err);
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

  async _syncInvoiceService() {
    this._invoiceService = null;
    const d = this._selected?.draft;
    if (!d || this._selected.source_changed) return;
    const request = d.invoice_review || {};
    if (request.state !== "requested" || request.requested_revision !== d.revision) return;
    try {
      const id = this._selected.booking.id;
      this._invoiceService = await this._api(
        "GET", "bookings/" + id + "/invoice-service/status"
      );
    } catch {
      this._invoiceService = {configured: false, unavailable: true};
    }
  }

  async _invoiceServiceAction(action) {
    const d = this._selected?.draft;
    if (!d || this._hasUnsaved || this._selected.source_changed) return;
    const number = this._selected.proposed_invoice_number;
    const payload = {revision: d.revision};
    if (action === "approve") {
      const phrase = "MUSTER FREIGEBEN " + number;
      const confirmed = window.prompt(
        "Ausschließlich diese DEMO-Mustervorschau freigeben (keine Rechnung ausstellen):\n" +
        phrase + "\n\nBitte den gesamten Text eingeben:"
      );
      if (confirmed !== phrase) return;
      payload.confirmation = confirmed;
    } else if (action === "correction") {
      const reason = window.prompt(
        "Korrekturbegründung für die bisherige Musterfassung (10 bis 500 Zeichen):"
      );
      if (reason === null || reason.trim().length < 10 || reason.length > 500) return;
      payload.reason = reason.trim();
    } else if (action === "archive") {
      if (!window.confirm(
        "Nur die bereits freigegebene DEMO-Mustervorschau privat archivieren? " +
        "Dies ist KEINE Rechnungsausstellung."
      )) return;
    } else if (action === "build") {
      if (!window.confirm(
        "Nur eine DEUTLICH als DEMO markierte ZUGFeRD-Mustervorschau erzeugen? " +
        "Es wird KEINE echte Rechnung erstellt oder versendet."
      )) return;
    }
    await this._run(async () => {
      await this._api("POST",
        "bookings/" + this._selected.booking.id + "/invoice-service/" + action,
        payload);
      await this._syncInvoiceService();
    });
  }

  async _downloadDemoPdf() {
    if (!this._selected || this._hasUnsaved || this._selected.source_changed) return;
    await this._run(async () => {
      const result = await this._api(
        "GET", "bookings/" + this._selected.booking.id + "/invoice-service/pdf"
      );
      if (!result.test_only || result.invoice_issued !== false ||
          !result.pdf_base64 || !result.filename.startsWith("DEMO-")) {
        throw new Error("Ungültiger DEMO-PDF-Status");
      }
      const binary = atob(result.pdf_base64);
      const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
      const blob = new Blob([bytes], {type: "application/pdf"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    });
  }

  async _requestDemoInvoicePreview() {
    const d = this._selected?.draft;
    if (!d || this._hasUnsaved || this._selected.source_changed) return;
    if (!window.confirm(
      "Nur eine ZUGFeRD-MUSTERVORSCHAU für diese gespeicherte Revision anfordern? " +
      "Es wird KEINE Rechnung ausgestellt oder an Gäste versendet."
    )) return;
    await this._run(async () => {
      const id = this._selected.booking.id;
      await this._api("POST", "bookings/" + id + "/preview-request", {
        revision: d.revision
      });
      this._selected = await this._api("GET", "bookings/" + id);
      await this._syncInvoiceService();
    });
  }

  async _exportInvoiceDraft() {
    if (!this._selected || this._hasUnsaved || this._selected.source_changed) return;
    await this._run(async () => {
      const id = this._selected.booking.id;
      const payload = await this._api("GET", "bookings/" + id + "/invoice-export");
      const file = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"});
      const address = URL.createObjectURL(file);
      const element = document.createElement("a");
      element.href = address;
      element.download = "mittelhof-invoice-draft-" + id + ".json";
      element.click();
      URL.revokeObjectURL(address);
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

  _renderInvoicePreview(invoice, preflight) {
    const esc = MittelhofGuestCard.esc;
    const lines = Array.isArray(invoice.line_items) ? invoice.line_items : [];
    const entries = lines.map((line) => '<tr><td>' +
      esc(line.description || '') +
      (line.quantity && line.quantity > 1 ? ' (' + esc(line.quantity) + ' ×)' : '') +
      (line.position_type === "stay_discount" && line.discount_nights ?
        ' · ' + esc(line.discount_nights) + ' Nächte' : '') +
      '</td><td>' + esc(line.tax_rate || 'offen') +
      '</td><td class="money">' + esc(line.gross || '0.00') + ' €</td></tr>').join('');
    const outstanding = preflight ? preflight.outstanding : '—';
    return '<section class="invoice-preview" aria-label="Nicht rechtsverbindliche Rechnungsvorschau">' +
      '<div class="invoice-head"><img class="invoice-logo" src="/local/smoobu_mittelhof/invoice-logo.png" alt="Ferienhaus Mittelhof" />' +
      '<div><strong>RECHNUNGSVORSCHAU</strong><small>ENTWURF · nicht ausgestellt · keine Rechnungsnummer</small></div></div>' +
      '<div class="invoice-recipient"><small>Rechnungsempfänger</small><strong>' +
      esc(invoice.recipient_name || 'Noch nicht eingetragen') + '</strong>' +
      '<div class="multiline">' + esc(invoice.recipient_address || 'Anschrift fehlt') + '</div></div>' +
      '<p class="multiline">' + esc(invoice.description || '') + '</p>' +
      '<table><thead><tr><th>Leistung</th><th>Steuer %</th><th>Brutto</th></tr></thead>' +
      '<tbody>' + entries + '</tbody></table>' +
      '<div class="invoice-totals"><div>Gesamt <strong>' + esc(invoice.total_gross) +
      ' €</strong></div><div>Bereits bezahlt <strong>' + esc(invoice.paid_amount) +
      ' €</strong></div><div>Offen <strong>' + esc(outstanding) + ' €</strong></div></div>' +
      '<p class="multiline">' + esc(invoice.payment_note || '') + '</p>' +
      '<small>Zahlungs- und Steuerdaten müssen vor Rechnungsausstellung überprüft werden.</small></section>';
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
    const review = d.invoice_review || {};
    const previewRequested = review.state === "requested" &&
      review.requested_revision === d.revision;
    html += '<p class="meta">Entwurf Revision ' + esc(d.revision) + ' · Nachricht: ' +
      esc(msg.status) + ' · Rechnung: ' + esc(inv.status) + '</p>' +
      '<p><strong>Geplante Rechnungsnummer:</strong> ' +
      esc(selected.proposed_invoice_number || 'Hausnummer in HA-Unterkunftszuordnung prüfen') +
      ' · Aufbau: Hausnummer + Anreise JJJJMMTT</p>';
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
    const service = this._invoiceService;
    if (previewRequested) {
      const serviceLabel = service?.unavailable ? 'Dienst nicht erreichbar' :
        !service?.configured ? 'Dienst nicht konfiguriert' :
        service.preview_created ? ('Vorhandenes Muster: ' + esc(service.review_state) +
        (service.pdfa_validated ? ' · PDF/A geprüft' : ' · PDF/A noch offen') +
        (service.archived ? ' · privat archiviert' : ' · nicht archiviert')) :
        'Bereit zur DEMO-Erzeugung';
      html += '<div class="preflight"><h4>Privater ZUGFeRD-Musterrechnungsdienst</h4>' +
        '<p>' + serviceLabel + '</p>' +
        '<p class="meta">Nur DEMO, keine finale Rechnungsnummer, keine Ausstellung, kein Gastversand.</p>' +
        '</div>';
    }
    html += '<p class="meta">ZUGFeRD-Musterprüfung: ' +
      (previewRequested ? 'für Revision ' + esc(d.revision) + ' angefordert' :
        'noch nicht angefordert bzw. nach Bearbeitung ungültig') +
      '. Keine endgültige Rechnungsfreigabe.</p>';
    if (selected.source_changed) html += '<div class="warning">Buchung seit Entwurf verändert. Bitte erneut vorbereiten und prüfen.</div>';
    if (!this._inbox?.message_send_enabled) html += '<p class="warning">Echter Gastversand ist in den HA-Integrationsoptionen deaktiviert.</p>';
    html += this._renderInvoicePreview(inv, pf);
    html += '<div class="edit-grid"><section><h4>Rechnungsentwurf (noch keine Rechnung)</h4>' +
      '<p><img class="logo" src="/local/smoobu_mittelhof/invoice-logo.png" alt="Ferienhaus Mittelhof – Logo" /></p>' +
      this._field("recipient_name", "Rechnungsempfänger", inv.recipient_name) +
      this._field("recipient_address", "Freitext-Anschrift (optional, nicht EN16931)", inv.recipient_address, true) +
      this._field("recipient_street", "Straße und Hausnummer", inv.recipient_street) +
      this._field("recipient_postal_code", "Postleitzahl", inv.recipient_postal_code) +
      this._field("recipient_city", "Ort", inv.recipient_city) +
      this._field("recipient_country", "Ländercode (DE, NL, FR ...)", inv.recipient_country) +
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
      this._positionEditor(inv) +
      '<p class="warning">Nur DEMO-Mustervorschau im privaten Rechnungsdienst; keine echte Ausstellung oder Versand.</p>' +
      '</section><section><h4>Nachrichtenentwurf</h4>' +
      this._field("subject", "Betreff", msg.subject) +
      this._field("body", "Nachricht", msg.body, true) +
      '<p>Die Nachricht wird über Smoobu als Text gesendet. Es wird kein Rechnungsanhang mitgeschickt.</p>' +
      '</section></div><div class="actions">' +
      '<button data-op="prepare">Mit aktuellem Buchungsstand abgleichen</button>' +
      '<button data-op="save">Änderungen speichern</button>' +
      '<button data-op="preview-request" ' +
      (!selected.source_changed && selected.proposed_invoice_number &&
       !previewRequested && pf && !pf.errors?.length ? "" : "disabled") +
      '>ZUGFeRD-Musterprüfung anfordern (keine Ausstellung)</button>' +
      '<button data-op="invoice-export" ' +
      (!selected.source_changed && selected.proposed_invoice_number &&
        previewRequested ? "" : "disabled") +
      '>Angeforderten Musterentwurf exportieren (JSON, personenbezogen)</button>' +
      '<button data-op="demo-build" ' +
      (previewRequested && service?.configured && !service.preview_created ? "" : "disabled") +
      '>DEMO-ZUGFeRD-PDF erzeugen</button>' +
      '<button data-op="demo-download" ' +
      (previewRequested && service?.pdf_available ? "" : "disabled") +
      '>DEMO-PDF herunterladen</button>' +
      '<button data-op="demo-verify" ' +
      (previewRequested && service?.preview_created && service.review_state === "pending_review" &&
       !service.pdfa_validated ? "" : "disabled") +
      '>PDF/A-3b unabhängig prüfen</button>' +
      '<button data-op="demo-approve" ' +
      (previewRequested && service?.pdfa_validated && service.review_state === "pending_review" ? "" : "disabled") +
      '>Mustervorschau manuell freigeben</button>' +
      '<button data-op="demo-archive" ' +
      (previewRequested && service?.review_state === "approved_preview" && !service.archived ? "" : "disabled") +
      '>Freigegebenes DEMO-Muster privat archivieren</button>' +
      '<button data-op="demo-correction" ' +
      (previewRequested && service?.review_state === "approved_preview" ? "" : "disabled") +
      '>Musterkorrektur begründet anfordern</button>' +
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
      '.edit-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.position-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;border:1px solid var(--divider-color);padding:8px;margin:8px 0;border-radius:6px}.position-row button{align-self:end}label{display:flex;flex-direction:column;gap:3px;margin:10px 0;font-size:13px}' +
      'input,textarea,select{box-sizing:border-box;width:100%;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);padding:8px;border-radius:6px;font:inherit}' +
      'textarea{min-height:80px}.checkbox{flex-direction:row;align-items:center}.checkbox input{width:auto}' +
      'button{cursor:pointer;border:1px solid var(--divider-color);border-radius:7px;padding:9px;background:var(--secondary-background-color);color:var(--primary-text-color)}' +
      'button:disabled{opacity:.45;cursor:not-allowed}.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.send{border-color:var(--success-color,#2a8)}' +
      '.invoice-preview{border:1px solid var(--divider-color);padding:18px;margin:15px 0;border-radius:9px;max-width:700px;background:var(--card-background-color)}.invoice-head{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:20px;flex-wrap:wrap}.invoice-head div{display:flex;flex-direction:column;gap:4px}.invoice-head small,.invoice-preview small{color:var(--secondary-text-color)}.invoice-logo{max-width:180px;max-height:90px;object-fit:contain}.invoice-recipient{display:flex;flex-direction:column;margin:12px 0 20px;gap:4px}.multiline{white-space:pre-wrap;overflow-wrap:anywhere}.invoice-preview table{width:100%;border-collapse:collapse}.invoice-preview th{text-align:left;font-size:12px}.invoice-preview td,.invoice-preview th{border-bottom:1px solid var(--divider-color);padding:7px 4px}.invoice-preview .money{text-align:right}.invoice-totals{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:15px 0}.invoice-totals div{display:flex;flex-direction:column;gap:4px}.preflight{border:1px solid var(--divider-color);padding:10px;border-radius:8px;margin:10px 0}.warning{border-left:3px solid #c9943c;padding:8px;color:var(--primary-text-color)}.logo{max-width:220px;max-height:90px;object-fit:contain}' +
      '@media(max-width:850px){.layout,.edit-grid{grid-template-columns:1fr}.thread-list{max-height:240px}}' +
      '</style><ha-card><header><h2>Gäste & Rechnungsentwürfe</h2>' +
      '<button data-op="refresh" ' + (this._busy ? "disabled" : "") + '>Aktualisieren</button></header>' +
      (this._error ? '<p class="warning" role="alert">' + esc(this._error) + '</p>' : '') +
      '<div class="layout"><aside>' + this._renderInbox() + '</aside><main>' +
      this._renderBooking() + '</main></div></ha-card>';
    this.shadowRoot.querySelectorAll('[data-field]').forEach((el) =>
      el.addEventListener("input", () => this._markUnsaved()));
    this.shadowRoot.querySelectorAll('[data-remove-position]').forEach((el) =>
      el.addEventListener("click", () => {
        el.closest('[data-position-row]').remove();
        this._markUnsaved();
      }));
    this.shadowRoot.querySelector('[data-add-position]')?.addEventListener(
      "click", () => this._addPosition());
    this.shadowRoot.querySelector('[data-use-position-total]')?.addEventListener(
      "click", () => {
        try {
          const total = this._positionSumText();
          this.shadowRoot.querySelector('[data-field="total_gross"]').value = total;
          const info = this.shadowRoot.querySelector('[data-position-total]');
          if (info) info.textContent = "Positionssumme: " + total + " €";
          this._markUnsaved();
        } catch (err) { window.alert(String(err.message || err)); }
      });
    this.shadowRoot.querySelectorAll('.logo,.invoice-logo').forEach((logo) =>
      logo.addEventListener("error", () => { logo.style.display = "none"; }));
    this.shadowRoot.querySelectorAll('[data-booking]').forEach((el) =>
      el.addEventListener("click", () => this._open(el.dataset.booking)));
    this.shadowRoot.querySelectorAll('[data-op]').forEach((el) =>
      el.addEventListener("click", () => {
        const actions = { refresh: () => this._loadInbox(), prepare: () => this._prepare(),
          save: () => this._save(), "preview-request": () => this._requestDemoInvoicePreview(),
          "invoice-export": () => this._exportInvoiceDraft(),
          "demo-build": () => this._invoiceServiceAction("build"),
          "demo-verify": () => this._invoiceServiceAction("verify"),
          "demo-approve": () => this._invoiceServiceAction("approve"),
          "demo-archive": () => this._invoiceServiceAction("archive"),
          "demo-correction": () => this._invoiceServiceAction("correction"),
          "demo-download": () => this._downloadDemoPdf(),
          regenerate: () => this._action("regenerate"),
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
