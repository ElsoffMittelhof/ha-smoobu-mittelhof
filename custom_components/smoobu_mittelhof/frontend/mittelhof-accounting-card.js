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
  }
  setConfig(config) { this._config = config || {}; }
  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) { this._loaded=true; void this._refresh(); }
  }
  getCardSize() { return 10; }
  static esc(s) { return String(s??"").replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  async _api(method, path, data) {
    return this._hass.callApi(method, "smoobu_mittelhof/guest/v1/"+path, data);
  }
  async _run(fn) {
    if(this._busy)return;
    this._busy=true; this._error=""; this._render();
    try { await fn(); } catch(e) { this._error=String(e?.message||e); }
    finally {this._busy=false;this._render();}
  }
  async _refresh() {
    await this._run(async()=>{
      this._from=this.shadowRoot.querySelector("[data-from]")?.value||this._from;
      this._to=this.shadowRoot.querySelector("[data-to]")?.value||this._to;
      const path="search-bookings?from="+encodeURIComponent(this._from)+"&to="+encodeURIComponent(this._to);
      const [search,ledger]=await Promise.all([this._api("GET",path),this._api("GET","accounting")]);
      this._search=search;
      this._records=ledger.records||[];
    });
  }
  async _open(id) {
    await this._run(async()=>{
      this._selected=await this._api("GET","bookings/"+encodeURIComponent(id)+"/accounting");
    });
  }
  async _review() {
    const current=this._selected;
    if(!current || current.source_changed)return;
    const rates=Array.from(this.shadowRoot.querySelectorAll("[data-rate]")).map(x=>x.value);
    if(rates.length!==current.source.rows.length) {this._error="Steuersätze unvollständig";this._render();return;}
    if(!window.confirm("Alle Steuersätze fachlich geprüft? Der interne Buchhaltungsbeleg ist keine Gastrechnung."))return;
    await this._run(async()=>{
      const id=current.source.booking_id;
      await this._api("POST","bookings/"+id+"/accounting",{
        source_fingerprint:current.source.source_fingerprint,
        rates, confirm_warnings:true, confirm_tax_review:true,
      });
      this._selected=await this._api("GET","bookings/"+id+"/accounting");
      this._records=(await this._api("GET","accounting")).records||[];
    });
  }
  async _download() {
    const selected=this._selected;
    if(!selected || selected.source_changed)return;
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
  async _markUploaded() {
    const selected=this._selected;
    if(!selected || selected.source_changed || !selected.record)return;
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
    const counts={ready:0,uploaded_manually:0};
    for(const x of this._records)if(counts[x.status]!==undefined)counts[x.status]++;
    const items=(this._search?.bookings||[]).map(b=>{
      const rec=this._records.find(x=>x.booking_id===String(b.booking_id));
      const state=rec?.status==="uploaded_manually"?"Hochgeladen":rec?.status==="ready"?"Bereit":"Prüfung offen";
      return '<button data-booking="'+e(b.booking_id)+'">'+e(b.arrival)+' · '+e(b.house)+' · '+e(b.guest||"Gast")+
        ' · '+e(b.channel||"Direkt")+' ['+state+']</button>';
    }).join("");
    const rows=s?.rows?.map((r,i)=>'<div class="line"><div><strong>'+e(r.description)+'</strong><small>'+
      e(r.gross)+' € · '+e(r.quantity)+' × Quelle · Vorschlag: '+e(r.suggested_tax_rate||"unbekannt")+'%</small></div>'+
      '<select data-rate="'+i+'"><option value="">USt prüfen</option>'+
      ["0","7","19"].map(rate=>'<option value="'+rate+'">'+rate+' %</option>').join("")+'</select></div>').join("")||"";
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
        .line{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--divider-color,#ddd)}
        small{display:block;opacity:.75}.actions{display:flex;flex-wrap:wrap;gap:9px;margin:14px 0}
        .error{padding:12px;color:var(--error-color,#b00)}.warning{padding:9px;background:var(--secondary-background-color,#eee);border-radius:8px;margin:8px 0}
        @media(max-width:800px){.grid{grid-template-columns:1fr}.panel{padding:10px}}
      </style>
      <ha-card>
        <h2>Buchhaltung · Lexware L</h2>
        <p>Interne Buchungsbelege, keine Rechnungen und kein Zahlungsabgleich. Lexware bleibt führend.</p>
        <div class="actions">
          <label>Von <input type="date" data-from value="${e(this._from)}"></label>
          <label>Bis <input type="date" data-to value="${e(this._to)}"></label>
          <button data-refresh ${this._busy?"disabled":""}>Buchungen suchen</button>
        </div>
        <p>${this._search?.total||0} Buchungen · ${counts.ready} geprüft · ${counts.uploaded_manually} manuell hochgeladen</p>
        ${this._error?'<div class="error">'+e(this._error)+'</div>':""}
        <div class="grid">
          <section class="panel"><strong>Buchungen</strong><div class="items">${items||"Keine Buchungen für diesen Zeitraum"}</div></section>
          <section class="panel"><strong>Belegprüfung</strong>
            ${s?`
              <p><strong>${e(s.house)} · ${e(s.guest)}</strong><br>${e(s.arrival)} bis ${e(s.departure)} · ${e(s.channel)}</p>
              <p><strong>Gastbrutto: ${e(s.total_gross)} €</strong><br><small>Keine Aussage zum tatsächlichen Zahlungseingang</small></p>
              ${this._selected.source_changed?'<p class="error">Buchung geändert: alter Beleg gesperrt. Nach Lexware-Upload Korrekturfall manuell klären.</p>':""}
              ${(s.warnings||[]).map(w=>'<p class="warning">'+e(w)+'</p>').join("")}
              ${rows}
              <div class="actions">
                <button data-review ${this._busy||this._selected.source_changed?"disabled":""}>Steuern prüfen und Beleg freigeben</button>
                <button data-pdf ${this._busy||!record||this._selected.source_changed?"disabled":""}>PDF herunterladen</button>
                <button data-upload ${this._busy||!record||this._selected.source_changed||record.status==="uploaded_manually"?"disabled":""}>In Lexware hochgeladen</button>
              </div>
              <small>Status: ${e(record?.status||"Noch nicht geprüft")}. Der Download verändert keine Zahlungen und erfasst nichts in Lexware.</small>
              `: '<p>Buchung auswählen, Steuerzuordnung prüfen und PDF erzeugen.</p>'}
          </section>
        </div>
      </ha-card>`;
    this.shadowRoot.querySelector("[data-refresh]")?.addEventListener("click",()=>void this._refresh());
    this.shadowRoot.querySelectorAll("[data-booking]").forEach(el=>
      el.addEventListener("click",()=>void this._open(el.dataset.booking)));
    this.shadowRoot.querySelector("[data-review]")?.addEventListener("click",()=>void this._review());
    this.shadowRoot.querySelector("[data-pdf]")?.addEventListener("click",()=>void this._download());
    this.shadowRoot.querySelector("[data-upload]")?.addEventListener("click",()=>void this._markUploaded());
  }
}
if (!customElements.get("mittelhof-accounting-card"))
  customElements.define("mittelhof-accounting-card", MittelhofAccountingCard);
