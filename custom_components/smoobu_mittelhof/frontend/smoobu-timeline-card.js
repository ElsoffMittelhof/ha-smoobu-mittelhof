/*
 * Smoobu Timeline Card for Home Assistant
 * Version 0.3.0
 *
 * Uses the response-capable service from the custom integration:
 *   smoobu_mittelhof.get_bookings
 *
 * No external frontend dependencies.
 */

class SmoobuTimelineCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._bookings = [];
    this._loading = false;
    this._error = null;
    this._selected = null;
    this._timer = null;
    this._lastFetch = 0;
    this._days = 21;
    this._offsetDays = -1;
    this._connected = false;
  }

  static getStubConfig() {
    return {
      title: "Smoobu Belegungsplan",
      days: 21,
      start_offset_days: -1,
      refresh_minutes: 30,
      houses: [
        { name: "Apartment A", house: "Apartment A", calendar_entity: "calendar.apartment_a_buchungen" },
        { name: "Apartment B", house: "Apartment B", calendar_entity: "calendar.apartment_b_buchungen" },
      ],
    };
  }

  setConfig(config) {
    if (!config) throw new Error("Konfiguration fehlt");

    const houses = Array.isArray(config.houses) && config.houses.length
      ? config.houses
      : SmoobuTimelineCard.getStubConfig().houses;

    this._config = {
      title: config.title || "Smoobu Belegungsplan",
      days: this._clampInt(config.days, 7, 60, 21),
      start_offset_days: this._clampInt(config.start_offset_days, -60, 365, -1),
      refresh_minutes: this._clampInt(config.refresh_minutes, 0, 1440, 30),
      show_channel: config.show_channel !== false,
      show_price: config.show_price === true,
      show_people: config.show_people !== false,
      compact: config.compact === true,
      houses: houses.map((item) => ({
        name: item.name || item.house || "Unterkunft",
        house: item.house || item.name || "Unterkunft",
        calendar_entity: item.calendar_entity || null,
      })),
    };

    this._days = this._config.days;
    this._offsetDays = this._config.start_offset_days;
    this._selected = null;
    this._bookings = [];
    this._error = null;

    this._render();
    this._restartTimer();
    this._queueFetch(true);
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    if (!this._bookings.length && !this._loading) {
      this._queueFetch(false);
    }
  }

  connectedCallback() {
    this._connected = true;
    this._restartTimer();
    this._render();
    this._queueFetch(false);
  }

  disconnectedCallback() {
    this._connected = false;
    this._clearTimer();
  }

  getCardSize() {
    return this._config?.compact ? 4 : 6;
  }

  // Home Assistant Sections view:
  // Force this custom card to use the complete width of a wider section.
  getGridOptions() {
    return {
      columns: "full",
      min_columns: 12,
    };
  }

  _clampInt(value, min, max, fallback) {
    const n = Number.parseInt(value, 10);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }

  _clearTimer() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  _restartTimer() {
    this._clearTimer();
    const minutes = this._config?.refresh_minutes ?? 30;
    if (!this._connected || !minutes) return;
    this._timer = setInterval(() => this._queueFetch(false), minutes * 60 * 1000);
  }

  _queueFetch(force) {
    if (!this._connected || !this._hass || !this._config || this._loading) return;
    if (!force && this._lastFetch && Date.now() - this._lastFetch < 2500) return;
    this._fetchBookings();
  }

  _localDate(base = new Date()) {
    return new Date(base.getFullYear(), base.getMonth(), base.getDate());
  }

  _addDays(date, days) {
    const result = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    result.setDate(result.getDate() + days);
    return result;
  }

  _formatYmd(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  _parseDate(value) {
    if (!value) return null;
    const raw = String(value);
    const dateOnly = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (dateOnly) {
      return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
    }
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? null : this._localDate(date);
  }

  _daySerial(date) {
    return Math.floor(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000);
  }

  _dateRange() {
    const today = this._localDate();
    const start = this._addDays(today, this._offsetDays);
    const end = this._addDays(start, this._days);
    return { start, end };
  }

  async _fetchBookings() {
    if (!this._hass) return;

    this._loading = true;
    this._error = null;
    this._render();

    const { start, end } = this._dateRange();
    const request = {
      type: "call_service",
      domain: "smoobu_mittelhof",
      service: "get_bookings",
      service_data: {
        start_date: this._formatYmd(start),
        end_date: this._formatYmd(end),
      },
      return_response: true,
    };

    try {
      let raw;
      if (typeof this._hass.callWS === "function") {
        raw = await this._hass.callWS(request);
      } else if (this._hass.connection?.sendMessagePromise) {
        raw = await this._hass.connection.sendMessagePromise(request);
      } else {
        throw new Error("Home-Assistant-WebSocket API ist nicht verfügbar");
      }

      const response = this._extractResponse(raw);
      if (!response || !Array.isArray(response.bookings)) {
        throw new Error("Unerwartete Antwort von smoobu_mittelhof.get_bookings");
      }

      this._bookings = response.bookings
        .filter((b) => b && b.arrival && b.departure)
        .sort((a, b) => String(a.arrival).localeCompare(String(b.arrival)));
      this._lastFetch = Date.now();
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _extractResponse(raw) {
    if (!raw || typeof raw !== "object") return null;
    if (Array.isArray(raw.bookings)) return raw;
    if (raw.response && Array.isArray(raw.response.bookings)) return raw.response;
    if (raw.result && Array.isArray(raw.result.bookings)) return raw.result;
    if (raw.result?.response && Array.isArray(raw.result.response.bookings)) return raw.result.response;
    if (raw.service_response && Array.isArray(raw.service_response.bookings)) return raw.service_response;
    return null;
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _formatShortDate(value) {
    const date = value instanceof Date ? value : this._parseDate(value);
    if (!date) return "–";
    return new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit" }).format(date);
  }

  _formatLongDate(value) {
    const date = value instanceof Date ? value : this._parseDate(value);
    if (!date) return "–";
    return new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
  }

  _weekday(value) {
    return new Intl.DateTimeFormat("de-DE", { weekday: "short" })
      .format(value)
      .replace(".", "")
      .slice(0, 2);
  }

  _channelInfo(channel) {
    const raw = String(channel || "").trim();
    const lower = raw.toLowerCase();
    if (lower.includes("booking")) return { key: "booking", badge: "B", label: raw || "Booking.com" };
    if (lower.includes("airbnb")) return { key: "airbnb", badge: "A", label: raw || "Airbnb" };
    if (lower.includes("website") || lower.includes("direkt") || lower.includes("direct")) {
      return { key: "website", badge: "W", label: raw || "Website" };
    }
    return { key: "other", badge: raw ? raw.charAt(0).toUpperCase() : "•", label: raw || "Sonstiger Kanal" };
  }

  _eventGuest(booking) {
    return String(booking.guest || "").trim() || "Belegt";
  }

  _nights(booking) {
    const start = this._parseDate(booking.arrival);
    const end = this._parseDate(booking.departure);
    if (!start || !end) return null;
    return Math.max(0, this._daySerial(end) - this._daySerial(start));
  }

  _houseBookings(house) {
    return this._bookings.filter((b) => String(b.house || "") === String(house || ""));
  }

  _barHtml(booking, rangeStart, rangeEnd, houseIndex) {
    const arrival = this._parseDate(booking.arrival);
    const departure = this._parseDate(booking.departure);
    if (!arrival || !departure) return "";

    const startSerial = this._daySerial(rangeStart);
    const endSerial = this._daySerial(rangeEnd);
    const arrivalSerial = this._daySerial(arrival);
    const departureSerial = this._daySerial(departure);

    const visibleStart = Math.max(arrivalSerial, startSerial);
    const visibleEnd = Math.min(departureSerial, endSerial);
    if (visibleEnd <= visibleStart) return "";

    const startIndex = visibleStart - startSerial;
    const endIndex = visibleEnd - startSerial;
    const channel = this._channelInfo(booking.channel);
    const guest = this._eventGuest(booking);
    const startsBefore = arrivalSerial < startSerial;
    const endsAfter = departureSerial > endSerial;
    const classes = ["booking", `channel-${channel.key}`];
    if (startsBefore) classes.push("continues-left");
    if (endsAfter) classes.push("continues-right");

    const tooltip = [
      guest,
      booking.house || "",
      `${this._formatLongDate(arrival)} – ${this._formatLongDate(departure)}`,
      channel.label,
    ].filter(Boolean).join(" · ");

    return `
      <button
        class="${classes.join(" ")}"
        style="grid-column: ${startIndex + 2} / ${endIndex + 2}; grid-row: 1;"
        data-booking-id="${this._escape(booking.booking_id)}"
        data-house-index="${houseIndex}"
        title="${this._escape(tooltip)}"
      >
        ${this._config.show_channel ? `<span class="channel-badge">${this._escape(channel.badge)}</span>` : ""}
        <span class="booking-label">${this._escape(guest)}</span>
      </button>`;
  }

  _detailsHtml() {
    const booking = this._selected;
    if (!booking) return "";

    const channel = this._channelInfo(booking.channel);
    const nights = this._nights(booking);
    const people = Number(booking.adults || 0) + Number(booking.children || 0);
    const price = booking.price;

    return `
      <div class="details">
        <div class="details-head">
          <div>
            <strong>${this._escape(booking.house || "Buchung")}</strong>
            <span class="details-guest">${this._escape(this._eventGuest(booking))}</span>
          </div>
          <button class="icon-button close-details" title="Details schließen">×</button>
        </div>
        <div class="details-grid">
          <div><span>Anreise</span><strong>${this._escape(this._formatLongDate(booking.arrival))}</strong></div>
          <div><span>Abreise</span><strong>${this._escape(this._formatLongDate(booking.departure))}</strong></div>
          <div><span>Nächte</span><strong>${nights ?? "–"}</strong></div>
          ${this._config.show_people ? `<div><span>Personen</span><strong>${people || "–"}</strong></div>` : ""}
          <div><span>Kanal</span><strong>${this._escape(channel.label)}</strong></div>
          <div><span>Buchungs-ID</span><strong>${this._escape(booking.booking_id || "–")}</strong></div>
          ${this._config.show_price && price != null ? `<div><span>Preis</span><strong>${this._escape(price)} €</strong></div>` : ""}
        </div>
      </div>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    if (!this._config) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">Smoobu Timeline Card wird konfiguriert …</div></ha-card>`;
      return;
    }

    const { start, end } = this._dateRange();
    const startSerial = this._daySerial(start);
    const todaySerial = this._daySerial(this._localDate());
    const gridStyle = `grid-template-columns: var(--label-width) repeat(${this._days}, minmax(var(--day-width), 1fr));`;

    const days = [];
    for (let i = 0; i < this._days; i += 1) {
      const date = this._addDays(start, i);
      const serial = startSerial + i;
      days.push({
        date,
        isToday: serial === todaySerial,
        isWeekend: date.getDay() === 0 || date.getDay() === 6,
      });
    }

    const headerDays = days.map((item) => `
      <div class="day-head ${item.isToday ? "today" : ""} ${item.isWeekend ? "weekend" : ""}">
        <span>${this._escape(this._weekday(item.date))}</span>
        <strong>${this._escape(this._formatShortDate(item.date))}</strong>
      </div>`).join("");

    const rows = this._config.houses.map((house, houseIndex) => {
      const bars = this._houseBookings(house.house)
        .map((booking) => this._barHtml(booking, start, end, houseIndex))
        .join("");

      const backgrounds = days.map((item) => `
        <div class="day-cell ${item.isToday ? "today" : ""} ${item.isWeekend ? "weekend" : ""}"></div>`).join("");

      return `
        <div class="timeline-row" style="${gridStyle}">
          <button class="house-label" data-house-index="${houseIndex}" title="${this._escape(house.name)}">
            ${this._escape(house.name)}
          </button>
          ${backgrounds}
          ${bars || `<div class="empty-row" style="grid-column: 2 / ${this._days + 2};">frei</div>`}
        </div>`;
    }).join("");

    const rangeText = `${this._formatLongDate(start)} – ${this._formatLongDate(this._addDays(end, -1))}`;
    const updatedText = this._lastFetch
      ? new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" }).format(new Date(this._lastFetch))
      : "–";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          width: 100%;
          max-width: none;
          --label-width: 165px;
          --day-width: 44px;
          --line: var(--divider-color, rgba(127,127,127,.22));
          --muted: var(--secondary-text-color, #777);
          --card-bg: var(--ha-card-background, var(--card-background-color, #fff));
          --booking: #6fa0e8;
          --website: #c9dcfa;
          --airbnb: #ef8c8c;
          --other: #b9a7dd;
          --today: rgba(33, 150, 243, .10);
          --weekend: rgba(127, 127, 127, .055);
        }
        ha-card {
          overflow: hidden;
          width: 100%;
          max-width: none;
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 14px 16px 10px;
          border-bottom: 1px solid var(--line);
        }
        .title { font-size: 1.1rem; font-weight: 600; }
        .subtitle { margin-top: 2px; color: var(--muted); font-size: .82rem; }
        .controls { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
        button { font: inherit; }
        .control, .icon-button {
          border: 0;
          border-radius: 10px;
          background: var(--secondary-background-color, rgba(127,127,127,.11));
          color: var(--primary-text-color);
          cursor: pointer;
          min-height: 34px;
          padding: 0 10px;
        }
        .control:hover, .icon-button:hover { filter: brightness(.97); }
        .control.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        .status {
          padding: 8px 16px;
          color: var(--muted);
          font-size: .82rem;
          display: flex;
          justify-content: space-between;
          gap: 10px;
          align-items: center;
        }
        .error { color: var(--error-color, #db4437); }
        .scroll { overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; }
        .timeline {
          min-width: calc(var(--label-width) + (${this._days} * var(--day-width)));
          position: relative;
        }
        .timeline-header, .timeline-row {
          display: grid;
          position: relative;
          min-height: ${this._config.compact ? "42px" : "54px"};
        }
        .timeline-header { min-height: 48px; border-top: 1px solid var(--line); }
        .corner, .house-label {
          position: sticky;
          left: 0;
          z-index: 5;
          background: var(--card-bg);
          border: 0;
          border-right: 1px solid var(--line);
          display: flex;
          align-items: center;
          padding: 0 12px;
        }
        .corner { z-index: 8; color: var(--muted); font-size: .8rem; }
        .house-label {
          justify-content: flex-start;
          font-weight: 600;
          cursor: pointer;
          color: var(--primary-text-color);
          text-align: left;
        }
        .day-head, .day-cell {
          border-right: 1px solid var(--line);
        }
        .day-head {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          font-size: .72rem;
          color: var(--muted);
          gap: 2px;
        }
        .day-head strong { color: var(--primary-text-color); font-size: .8rem; }
        .day-head.weekend, .day-cell.weekend { background: var(--weekend); }
        .day-head.today, .day-cell.today { background: var(--today); }
        .timeline-row { border-top: 1px solid var(--line); }
        .day-cell { grid-row: 1; min-width: 0; }
        .booking {
          align-self: center;
          z-index: 3;
          height: ${this._config.compact ? "30px" : "36px"};
          margin: 0 3px;
          border: 0;
          border-radius: 18px;
          display: flex;
          align-items: center;
          gap: 7px;
          padding: 0 10px;
          min-width: 0;
          overflow: hidden;
          cursor: pointer;
          color: #182433;
          box-shadow: 0 1px 2px rgba(0,0,0,.10);
        }
        .booking.channel-booking { background: var(--booking); }
        .booking.channel-website { background: var(--website); }
        .booking.channel-airbnb { background: var(--airbnb); }
        .booking.channel-other { background: var(--other); }
        .booking.continues-left { border-top-left-radius: 4px; border-bottom-left-radius: 4px; }
        .booking.continues-right { border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
        .channel-badge {
          flex: 0 0 auto;
          width: 23px;
          height: 23px;
          border-radius: 50%;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: rgba(255,255,255,.76);
          font-size: .74rem;
          font-weight: 700;
        }
        .booking-label {
          min-width: 0;
          overflow: hidden;
          white-space: nowrap;
          text-overflow: ellipsis;
          font-size: .86rem;
        }
        .empty-row {
          grid-row: 1;
          align-self: center;
          padding-left: 10px;
          color: var(--muted);
          font-size: .78rem;
          pointer-events: none;
        }
        .legend {
          display: flex;
          gap: 12px;
          flex-wrap: wrap;
          padding: 10px 16px 14px;
          color: var(--muted);
          font-size: .78rem;
          border-top: 1px solid var(--line);
        }
        .legend-item { display: inline-flex; align-items: center; gap: 5px; }
        .legend-dot { width: 11px; height: 11px; border-radius: 50%; }
        .legend-dot.booking { background: var(--booking); }
        .legend-dot.website { background: var(--website); }
        .legend-dot.airbnb { background: var(--airbnb); }
        .legend-dot.other { background: var(--other); }
        .today-line {
          pointer-events: none;
          grid-row: 1 / ${this._config.houses.length + 2};
          width: 2px;
          justify-self: start;
          background: var(--primary-color);
          opacity: .65;
          z-index: 4;
        }
        .details {
          margin: 0 16px 14px;
          padding: 12px;
          border-radius: 12px;
          background: var(--secondary-background-color, rgba(127,127,127,.08));
        }
        .details-head { display:flex; align-items:center; justify-content:space-between; gap:12px; }
        .details-guest { margin-left: 8px; color: var(--muted); }
        .close-details { width: 34px; padding: 0; font-size: 1.3rem; }
        .details-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
          gap: 8px 14px;
          margin-top: 10px;
        }
        .details-grid div { display: flex; flex-direction: column; gap: 2px; }
        .details-grid span { color: var(--muted); font-size: .72rem; }
        .details-grid strong { font-size: .86rem; }
        @media (max-width: 700px) {
          :host { --label-width: 125px; --day-width: 42px; }
          .header { align-items: flex-start; flex-direction: column; }
          .controls { justify-content: flex-start; }
          .house-label { font-size: .82rem; padding-left: 8px; }
          .status { align-items: flex-start; flex-direction: column; }
        }
      </style>
      <ha-card>
        <div class="header">
          <div>
            <div class="title">${this._escape(this._config.title)}</div>
            <div class="subtitle">${this._escape(rangeText)}</div>
          </div>
          <div class="controls">
            <button class="control nav-prev" title="7 Tage zurück">◀</button>
            <button class="control nav-today">Heute</button>
            <button class="control nav-next" title="7 Tage vor">▶</button>
            ${[14, 21, 30, 45].map((n) => `<button class="control zoom ${this._days === n ? "active" : ""}" data-days="${n}">${n} T</button>`).join("")}
            <button class="control refresh" title="Neu von Smoobu laden">${this._loading ? "…" : "↻"}</button>
          </div>
        </div>
        <div class="status ${this._error ? "error" : ""}">
          <span>${this._error ? this._escape(this._error) : `${this._bookings.length} Buchung(en) im Zeitraum`}</span>
          <span>Stand ${this._escape(updatedText)}</span>
        </div>
        <div class="scroll">
          <div class="timeline">
            <div class="timeline-header" style="${gridStyle}">
              <div class="corner">Unterkunft</div>
              ${headerDays}
            </div>
            ${rows}
          </div>
        </div>
        ${this._detailsHtml()}
        ${this._config.show_channel ? `
          <div class="legend">
            <span class="legend-item"><i class="legend-dot booking"></i>Booking.com</span>
            <span class="legend-item"><i class="legend-dot website"></i>Website</span>
            <span class="legend-item"><i class="legend-dot airbnb"></i>Airbnb</span>
            <span class="legend-item"><i class="legend-dot other"></i>Andere</span>
          </div>` : ""}
      </ha-card>`;

    this._bindEvents();
  }

  _bindEvents() {
    const root = this.shadowRoot;
    if (!root) return;

    root.querySelector(".nav-prev")?.addEventListener("click", () => {
      this._offsetDays -= 7;
      this._selected = null;
      this._fetchBookings();
    });
    root.querySelector(".nav-next")?.addEventListener("click", () => {
      this._offsetDays += 7;
      this._selected = null;
      this._fetchBookings();
    });
    root.querySelector(".nav-today")?.addEventListener("click", () => {
      this._offsetDays = this._config.start_offset_days;
      this._selected = null;
      this._fetchBookings();
    });
    root.querySelector(".refresh")?.addEventListener("click", () => this._fetchBookings());

    root.querySelectorAll(".zoom").forEach((button) => {
      button.addEventListener("click", () => {
        this._days = this._clampInt(button.dataset.days, 7, 60, this._days);
        this._selected = null;
        this._fetchBookings();
      });
    });

    root.querySelectorAll(".booking").forEach((button) => {
      button.addEventListener("click", () => {
        const id = String(button.dataset.bookingId || "");
        this._selected = this._bookings.find((item) => String(item.booking_id || "") === id) || null;
        this._render();
      });
    });

    root.querySelector(".close-details")?.addEventListener("click", () => {
      this._selected = null;
      this._render();
    });

    root.querySelectorAll(".house-label").forEach((button) => {
      button.addEventListener("click", () => {
        const index = Number(button.dataset.houseIndex);
        const entityId = this._config.houses[index]?.calendar_entity;
        if (!entityId) return;
        this.dispatchEvent(new CustomEvent("hass-more-info", {
          bubbles: true,
          composed: true,
          detail: { entityId },
        }));
      });
    });
  }
}

if (!customElements.get("smoobu-timeline-card")) {
  customElements.define("smoobu-timeline-card", SmoobuTimelineCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "smoobu-timeline-card")) {
  window.customCards.push({
    type: "smoobu-timeline-card",
    name: "Smoobu Timeline Card",
    description: "Horizontale Smoobu-Belegungsübersicht für mehrere Ferienhäuser",
    preview: false,
  });
}

console.info("%c SMOOBU-TIMELINE-CARD %c v0.3.0 ", "color:white;background:#3f78b5;font-weight:700", "color:#3f78b5;background:#eef5ff");
