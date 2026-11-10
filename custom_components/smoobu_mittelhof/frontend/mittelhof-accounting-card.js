/* Mittelhof accounting for Lexware L: admin-only, review-before-export, no invoice issuance. */
class MittelhofAccountingCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._from = new Date(Date.now()-30*86400000).toISOString().slice(0,10);
    this._to = new Date(Date.now()+180*86400000).toISOString().slice(0,10);
    this._search = null;
    this._selected = null;
    this._records = [];
    this._error = "";
    this._busy = false;
    this._documentKind = "booking_record";
  }
  setConfig(config) { this._config = config || {}; }
  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) { this._loaded=true; void this._refresh(); }
  }
  getCardSize() { return 10; }
  static esc(s) { return String(s??"").replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  static errorText(error) {
    // HA callApi may supply a structured {message:{...}} response rather than
    // a JavaScript Error. Never show the useless "[object Object]" placeholder.
    const read = (value, depth=0) => {
      if (depth>5 || value == null) return "";
      if (typeof value==="string") return value.trim();
      if (typeof value==="number") return String(value);
      if (typeof value!=="object") return "";
      if (Array.isArray(value)) return value.map(v=>read(v,depth+1)).filter(Boolean).join("; ");
      for (const key of ["message","error","detail","text","body","description","reason"]) {
        const result=read(value[key],depth+1);
        if(result && result!=="[object Object]")return result;
      }
      if(typeof value.status==="number")return "HTTP "+value.status;
      if(typeof value.code==="number")return "HTTP "+value.code;
      return "";
    };
    const detail=read(error);
    const status=error?.status||error?.code;
    const prefix=Number.isInteger(status)?"HTTP "+status+": ":"";
    return (prefix+detail).trim()||"Die Anfrage konnte nicht verarbeitet werden. Home-Assistant-Protokoll prüfen.";
  }
  async _api(method, path, data) {
    const endpoint="smoobu_mittelhof/guest/v1/"+path;
    try {
      return await this._hass.callApi(method, endpoint, data);
    } catch(error) {
      // HTTP 404 may be a missing HA route OR a booking not found within
      // the handler. Include the method + endpoint class for diagnosis,
      // without exposing the booking ID, guest name or authentication data.
      const endpointClass=endpoint
        .replace(/\/bookings\/\d+(?=\/|$)/g,"/bookings/{id}")
        .replace(/\?.*$/,"");
      const status=error?.status??error?.code;
      const message=MittelhofAccountingCard.errorText(error);
      if (status===404 || /(?:^|\s)404(?:\s|$)/.test(message)) {
        throw new Error("HTTP 404 bei "+method.toUpperCase()+" /api/"+
          endpointClass+" – Endpunkt oder Smoobu-Buchung nicht gefunden. "+
          "Home Assistant neu starten und installierte Integrationsversion prüfen.");
      }
      throw new Error(method.toUpperCase()+" /api/"+endpointClass+": "+message);
    }
  }
  async _run(fn) {
    if(this._busy)return;
    this._busy=true; this._error=""; this._render();
    try { await fn(); } catch(e) { this._error=MittelhofAccountingCard.errorText(e); }
    finally {this._busy=false;this._render();}
  }
  async _refresh() {
    // Read live date inputs BEFORE _run() calls _render(), which replaces them.
    // Otherwise every search silently restores the previous/default dates.
    const from=this.shadowRoot.querySelector("[data-from]")?.value ?? this._from;
    const to=this.shadowRoot.querySelector("[data-to]")?.value ?? this._to;
    this._from=from;
    this._to=to;
    const fromDate=new Date(from+"T00:00:00Z");
    const toDate=new Date(to+"T00:00:00Z");
    const days=(toDate-fromDate)/86400000;
    const datesValid=Number.isFinite(fromDate.getTime()) && Number.isFinite(toDate.getTime());
    if (!/^\d{4}-\d{2}-\d{2}$/.test(from) ||
        !/^\d{4}-\d{2}-\d{2}$/.test(to) ||
        !datesValid || !Number.isInteger(days) || days<0 || days>730 ||
        fromDate.toISOString().slice(0,10)!==from ||
        toDate.toISOString().slice(0,10)!==to) {
      this._error="Bitte einen gültigen Zeitraum von höchstens 731 Tagen wählen (Von ≤ Bis).";
      this._render();
      return;
    }
    await this._run(async()=>{
      const path="search-bookings?from="+encodeURIComponent(from)+"&to="+encodeURIComponent(to);
      const [search,ledger]=await Promise.all([this._api("GET",path),this._api("GET","accounting")]);
      this._search=search;
      this._records=ledger.records||[];
    });
  }
  async _open(id) {
    await this._run(async()=>{
      this._selected=await this._api("GET","bookings/"+encodeURIComponent(id)+"/accounting");
      this._documentKind=this._selected.record?.document_kind||this._selected.source.suggested_document_kind||"booking_record";
    });
  }
  _selectedEdits() {
    return [...this.shadowRoot.querySelectorAll("[data-line]")].filter(el =>
      el.querySelector("[data-include]")?.checked).map(el => ({
      source_index: Number(el.dataset.line),
      description: el.querySelector("[data-description]").value.trim(),
      gross: el.querySelector("[data-gross]").value.trim(),
      tax_rate: el.querySelector("[data-rate]").value
    }));
  }
  async _review() {
    const current=this._selected;
    if(!current||current.source_changed||this._documentKind!=="booking_record")return;
    const edits=this._selectedEdits();
    if(!edits.length || edits.some(x=>!x.tax_rate)) {
      this._error="Mindestens eine Gastposition mit geprüftem Steuersatz erforderlich";
      this._render();return;
    }
    if(!window.confirm("Gastpositionen, Änderungen und sämtliche Umsatzsteuersätze geprüft? Es wird KEINE Gastrechnung erstellt."))return;
    await this._run(async()=>{
      const id=current.source.booking_id;
      await this._api("POST","bookings/"+id+"/accounting",{
        source_fingerprint:current.source.source_fingerprint,
        document_kind:"booking_record",
        edits:edits.map(({tax_rate,...rest})=>rest),
        rates:edits.map(x=>x.tax_rate),
        confirm_warnings:true,confirm_tax_review:true
      });
      this._selected=await this._api("GET","bookings/"+id+"/accounting");
      this._records=(await this._api("GET","accounting")).records||[];
    });
  }
  async _referenceInvoice() {
    const current=this._selected;
    if(!current||current.source_changed||this._documentKind!=="invoice")return;
    const ref=this.shadowRoot.querySelector("[data-invoice-ref]")?.value?.trim()||"";
    if(!ref){this._error="Externe Rechnungsnummer oder Belegreferenz fehlt";this._render();return;}
    if(!window.confirm("Diese Rechnung ist bereits tatsächlich ausgestellt und in der Buchhaltung erfasst? Es wird hier keine Rechnung erzeugt."))return;
    await this._run(async()=>{
      const id=current.source.booking_id;
      await this._api("POST","bookings/"+id+"/accounting/invoice-reference",{
        source_fingerprint:current.source.source_fingerprint,
        invoice_reference:ref,confirm_existing_invoice:true
      });
      this._selected=await this._api("GET","bookings/"+id+"/accounting");
      this._records=(await this._api("GET","accounting")).records||[];
    });
  }
  async _download() {
    const selected=this._selected;
    if(!selected || selected.source_changed || selected.record?.document_kind==="invoice")return;
    await this._run(async()=>{
      const result=await this._api("GET","bookings/"+selected.source.booking_id+"/accounting/pdf");
      const raw=atob(result.pdf_base64);
      const bytes=new Uint8Array(raw.length);
      for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
      const blob=new Blob([bytes],{type:"application/pdf"});
      const url=URL.createObjectURL(blob);
      const a=document.createElement("a");
      a.href=url;a.download=result.filename;this.shadowRoot.appendChild(a);a.click();a.remove();
      setTimeout(()=>URL.revokeObjectURL(url),2000);
    });
  }
  async _downloadBundle() {
    const visible=new Set((this._search?.bookings||[]).map(x=>String(x.booking_id)));
    const ids=this._records.filter(x=>visible.has(x.booking_id)&&
      ["ready","uploaded_manually"].includes(x.status) && x.document_kind!=="invoice").map(x=>x.booking_id).slice(0,25);
    if(!ids.length){this._error="Keine freigegebenen Buchhaltungsbelege im gewählten Zeitraum";this._render();return;}
    if(!window.confirm(ids.length+" bereits geprüfte PDF-Belege als ZIP exportieren? Keine Lexware-Erfassung wird dadurch markiert."))return;
    await this._run(async()=>{
      const result=await this._api("POST","accounting/bundle",{booking_ids:ids});
      const raw=atob(result.zip_base64);
      const bytes=new Uint8Array(raw.length);
      for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
      const blob=new Blob([bytes],{type:"application/zip"});
      const url=URL.createObjectURL(blob);
      const a=document.createElement("a");
      a.href=url;a.download=result.filename;this.shadowRoot.appendChild(a);a.click();a.remove();
      setTimeout(()=>URL.revokeObjectURL(url),2000);
    });
  }
  async _markUploaded() {
    const selected=this._selected;
    if(!selected || selected.source_changed || !selected.record || selected.record.document_kind==="invoice")return;
    if(!window.confirm("Hast du das PDF wirklich als Einnahmenbeleg in Lexware Office L hochgeladen und geprüft?"))return;
    await this._run(async()=>{
      const id=selected.source.booking_id;
      await this._api("POST","bookings/"+id+"/accounting/uploaded",{
        sha256:selected.record.sha256, confirm_manual_upload:true,
      });
      this._selected=await this._api("GET","bookings/"+id+"/accounting");
      this._records=(await this._api("GET","accounting")).records||[];
    });
  }
  _render() {
    const e=MittelhofAccountingCard.esc;
    const s=this._selected?.source, record=this._selected?.record;
    const counts={ready:0,uploaded_manually:0,invoice_reference:0};
    const locked=record?.status==="uploaded_manually"||record?.status==="invoice_reference";
    const invoiceMode=this._documentKind==="invoice";
    for(const x of this._records)if(counts[x.status]!==undefined)counts[x.status]++;
    const items=(this._search?.bookings||[]).map(b=>{
      const rec=this._records.find(x=>x.booking_id===String(b.booking_id));
      const proposed=/tomas|direkt|direct/i.test(String(b.channel||""))?"invoice":"booking_record";
      const type=rec?.document_kind||proposed;
      const state=rec?.status==="invoice_reference"?"Rechnung "+rec.invoice_reference:
        rec?.status==="uploaded_manually"?"PDF hochgeladen":rec?.status==="ready"?"PDF bereit":
        type==="invoice"?"Rechnung vorgesehen":"Buchungsbeleg offen";
      return '<button data-booking="'+e(b.booking_id)+'">'+e(b.arrival)+' · '+e(b.house)+' · '+e(b.guest||"Gast")+
        ' · '+e(b.channel||"Direkt")+' ['+state+']</button>';
    }).join("");
    const reviewed=record?.reviewed_rows||[];
    const reviewedMap=new Map(reviewed.map(r=>[r.source_index,r]));
    const hasReviewed=reviewed.length>0;
    const rows=(s?.rows||[]).map(r=>{
      const old=reviewedMap.get(r.source_index);
      const included=!hasReviewed||Boolean(old);
      const desc=old?.description??r.description;
      const gross=old?.gross??r.gross;
      // Local operating default: all current guest services use 7%.
      // Existing reviewed snapshots retain their explicitly selected rates.
      const rate=old?.tax_rate??"7";
      return '<div class="line" data-line="'+r.source_index+'">'+
        '<label><input data-include type="checkbox" '+(included?'checked ':'')+(locked?'disabled':'')+'> Gastpreisposition</label>'+
        '<input data-description type="text" maxlength="160" value="'+e(desc)+'" '+(locked?'disabled':'')+'>'+
        '<div class="money"><input data-gross type="number" step="0.01" min="0.01" value="'+e(gross)+'" '+(locked?'disabled':'')+'>'+
        ' EUR <select data-rate '+(locked?'disabled':'')+'><option value="" disabled>USt auswählen</option>'+
        ["0","7","19"].map(value=>'<option value="'+value+'" '+(value===rate?'selected':'')+'>'+value+' %</option>').join("")+
        '</select></div></div>';
    }).join("");
    const ignored=(s?.ignored_settlement_lines||[]).map(r=>
      '<li>'+e(r.description)+' · '+e(r.gross)+' EUR ('+
        (r.reason==="platform_commission"?"Portalprovision separat":"Storno-Abrechnung, nicht Gastumsatz")+
      ')</li>').join("");
    const kindSelector='<label>Dokumentart <select data-kind '+(locked?'disabled':'')+'>'+
      '<option value="booking_record" '+(invoiceMode?'':'selected')+'>Buchhaltungsbeleg</option>'+
      '<option value="invoice" '+(invoiceMode?'selected':'')+'>Gastrechnung vorgesehen / referenzieren</option>'+
      '</select></label>';
    const invoiceDetails=record?.status==="invoice_reference"?
      '<p><strong>Vorhandene Gastrechnung: '+e(record.invoice_reference)+'</strong></p>':
      '<p>Rechnung vor Anreise außerhalb dieses Moduls erstellen. Sobald sie tatsächlich ausgestellt und in Lexware erfasst ist, ihre Rechnungsreferenz hinterlegen:</p>'+
      '<input type="text" maxlength="120" data-invoice-ref placeholder="Rechnungsnummer / Belegreferenz">';
    const detail=s?
      '<p><strong>'+e(s.house)+' · '+e(s.guest)+'</strong><br>'+e(s.arrival)+' bis '+e(s.departure)+' · '+e(s.channel)+'</p>'+
      '<p><strong>Belegtyp:</strong> '+e(s.accounting_type||"nicht verfügbar")+' · <strong>Belegnummer:</strong> '+e(s.document_number||"nicht verfügbar")+' · <strong>Leistungsdatum:</strong> '+e(s.service_date||"nicht verfügbar")+'</p>'+ 
      '<p><strong>Gastbrutto: '+e(s.total_gross)+' EUR</strong><small>Zahlungseingang nicht geprüft</small></p>'+
      '<p><strong>Belegdatum:</strong> '+e(s.document_date||"nicht verfügbar")+
      ' · <strong>Fälligkeitsdatum:</strong> '+e(s.due_date||"nicht verfügbar")+
      '<small>Beide aus Smoobu-Buchungsdatum (created-at), für Lexware L. Kein Nachweis einer offenen Forderung.</small></p>'+
      (this._selected.source_changed?'<p class="error">Smoobu-Buchung verändert. Alter Export gesperrt, in Lexware ggf. manuell korrigieren.</p>':'')+
      (this._selected.date_revision_required?'<p class="warning">Vorherige PDF-Revision enthält noch keine geprüften Buchungs-/Lexware-Datumsfelder. Bitte erneut prüfen; bereits in Lexware hochgeladene Belege nicht überschreiben.</p>':'')+
      kindSelector+
      (invoiceMode?
        '<p class="warning">Direktbuchung/TOMAS/Homepage-Überweisung: keine zweite Buchungs-PDF-Einnahme erfassen. Dieses Modul stellt keine Gastrechnung aus.</p>'+
        invoiceDetails+'<div class="actions"><button data-invoice '+
          (this._busy||locked||this._selected.source_changed?'disabled':'')+
          '>Bestehende Rechnung referenzieren</button></div>':
        (s.warnings||[]).map(w=>'<p class="warning">'+e(w)+'</p>').join("")+
        '<h4>Gastpreispositionen – abwählen oder bearbeiten</h4>'+rows+
        (ignored?'<details><summary>Separat behandelte Portal-/Stornopositionen</summary><ul>'+ignored+'</ul></details>':'')+
        '<p><small>Die ausgewählten Bruttobeträge müssen insgesamt exakt '+e(s.total_gross)+
        ' EUR ergeben. Nur Gastleistungen gehören hier hinein.</small></p>'+
        '<div class="actions"><button data-review '+(this._busy||locked||this._selected.source_changed?'disabled':'')+
        '>Steuern prüfen und PDF freigeben</button>'+
        '<button data-pdf '+(this._busy||!record||record.document_kind==="invoice"||this._selected.source_changed||this._selected.date_revision_required?'disabled':'')+
        '>PDF herunterladen</button>'+
        '<button data-upload '+(this._busy||!record||locked||this._selected.source_changed||this._selected.date_revision_required?'disabled':'')+
        '>In Lexware hochgeladen</button></div>'
      )+
      '<small>Status: '+e(record?.status||(invoiceMode?'Rechnung vorgesehen':'Noch nicht geprüft'))+'</small>':
      '<p>Bitte eine Buchung auswählen.</p>';
    this.shadowRoot.innerHTML=`
      <style>
        :host{display:block;font:inherit;color:var(--primary-text-color)}
        ha-card{display:block;box-sizing:border-box;width:100%;max-width:1480px;margin:auto;padding:16px}
        .grid{display:grid;grid-template-columns:minmax(260px,1fr) minmax(300px,1.4fr);gap:18px}
        .panel{min-width:0;border:1px solid var(--divider-color,#ddd);border-radius:12px;padding:14px}
        button,select,input{font:inherit;border-radius:8px;padding:9px;background:var(--card-background-color);color:inherit;border:1px solid var(--divider-color,#aaa)}
        button{cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}
        .items{display:flex;flex-direction:column;gap:6px;max-height:560px;overflow:auto;margin-top:12px}
        .items button{text-align:left}
        .line{display:grid;grid-template-columns:155px minmax(140px,1fr) auto;gap:9px;align-items:center;padding:10px 0;border-bottom:1px solid var(--divider-color,#ddd)}
        .money{display:flex;align-items:center;gap:7px}.money input{width:100px}.line input[type=text]{min-width:0}
        input[type=checkbox]{width:auto}
        small{display:block;opacity:.75}.actions{display:flex;flex-wrap:wrap;gap:9px;margin:14px 0}
        .error{padding:12px;color:var(--error-color,#b00)}.warning{padding:9px;background:var(--secondary-background-color,#eee);border-radius:8px;margin:8px 0}
        @media(max-width:850px){.grid{grid-template-columns:1fr}.panel{padding:10px}.line{grid-template-columns:1fr}.money{flex-wrap:wrap}}
      </style>
      <ha-card>
        <h2>Buchhaltung · Lexware L</h2>
        <p>Gastbrutto und Portalabrechnung getrennt. Bereits ausgestellte Rechnungen nur referenzieren; kein Zahlungsabgleich.</p>
        <div class="actions">
          <label>Von <input type="date" data-from value="${e(this._from)}"></label>
          <label>Bis <input type="date" data-to value="${e(this._to)}"></label>
          <button data-refresh ${this._busy?"disabled":""}>Buchungen suchen</button>
          <button data-bundle ${this._busy?"disabled":""}>Geprüfte PDFs als ZIP (max. 25)</button>
        </div>
        <p>${this._search?.total||0} Buchungen · ${counts.ready} PDFs geprüft · ${counts.uploaded_manually} hochgeladen · ${counts.invoice_reference} Rechnungen referenziert</p>
        ${this._error?'<div class="error">'+e(this._error)+'</div>':""}
        <div class="grid">
          <section class="panel"><strong>Buchungen</strong><div class="items">${items||"Keine Buchungen für diesen Zeitraum"}</div></section>
          <section class="panel"><strong>Belegprüfung</strong>
            ${detail}
          </section>
        </div>
      </ha-card>`;
    // Keep date selection even when HA updates or booking actions re-render the card.
    this.shadowRoot.querySelector("[data-from]")?.addEventListener("change",event=>{
      this._from=event.target.value;
    });
    this.shadowRoot.querySelector("[data-to]")?.addEventListener("change",event=>{
      this._to=event.target.value;
    });
    this.shadowRoot.querySelector("[data-refresh]")?.addEventListener("click",()=>void this._refresh());
    this.shadowRoot.querySelectorAll("[data-booking]").forEach(el=>
      el.addEventListener("click",()=>void this._open(el.dataset.booking)));
    this.shadowRoot.querySelector("[data-kind]")?.addEventListener("change",event=>{this._documentKind=event.target.value;this._render();});
    this.shadowRoot.querySelector("[data-invoice]")?.addEventListener("click",()=>void this._referenceInvoice());
    this.shadowRoot.querySelector("[data-review]")?.addEventListener("click",()=>void this._review());
    this.shadowRoot.querySelector("[data-bundle]")?.addEventListener("click",()=>void this._downloadBundle());
    this.shadowRoot.querySelector("[data-pdf]")?.addEventListener("click",()=>void this._download());
    this.shadowRoot.querySelector("[data-upload]")?.addEventListener("click",()=>void this._markUploaded());
  }
}
if (!customElements.get("mittelhof-accounting-card"))
  customElements.define("mittelhof-accounting-card", MittelhofAccountingCard);
