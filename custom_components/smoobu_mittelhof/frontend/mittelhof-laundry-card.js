/* Mittelhof v0.6 – HA-only warehouse card; no external network access. */
(() => {
  const labels={pillowcase:"Kopfkissenbezüge",flat_sheet:"Laken",duvet_cover:"Bettdeckenbezüge",
    bath_towel:"Badetücher",towel:"Handtücher",bath_mat:"Badvorleger"};
  const keys=Object.keys(labels);
  const houses=[["Haus 13",1046730],["Haus 14",1069726],["Haus 15",1069729]];
  function el(tag,text,cls) {
    const n=document.createElement(tag);
    if(text!=null)n.textContent=String(text);
    if(cls)n.className=cls;
    return n;
  }
  function numberField(key,value,max=100) {
    const row=el("label",null,"quantity");
    row.append(el("span",labels[key]));
    const i=el("input");
    i.type="number";i.min="0";i.max=String(max);i.step="1";i.required=true;
    i.value=String(value);i.dataset.key=key;
    row.append(i);return row;
  }
  function read(container) {
    const items={};
    for(const key of keys){
      const i=container.querySelector('input[data-key="'+key+'"]');
      const v=Number(i?.value);
      if(!Number.isSafeInteger(v)||v<0||v>Number(i.max))throw Error("Ungültige Menge: "+labels[key]);
      items[key]=v;
    }
    return items;
  }
  function simulation(stock,sets,extras){
    const used={},rest={},reorder={};
    if(!Number.isSafeInteger(sets)||sets<0||sets>8)throw Error("Sets müssen zwischen 0 und 8 liegen.");
    if(!stock||keys.some(k=>!Number.isSafeInteger(stock[k])||stock[k]<0))
      throw Error("Kein vollständiger Artikelbestand verfügbar.");
    for(const key of keys){
      used[key]=extras[key]+(key==="bath_mat"?0:sets);
      rest[key]=stock[key]-used[key];
      const target=key==="bath_mat"?6:24,threshold=key==="bath_mat"?2:12;
      reorder[key]=rest[key]<=threshold?Math.max(0,target-rest[key]):0;
    }
    if(!Object.values(used).some(v=>v>0))throw Error("Bitte mindestens einen Artikel auswählen.");
    return {used,rest,reorder,possibleSets:Math.max(0,Math.min(...keys.slice(0,5).map(k=>rest[k]))),
      valid:keys.every(k=>rest[k]>=0)};
  }
  class MittelhofLaundryCard extends HTMLElement {
    constructor(){super();this.attachShadow({mode:"open"});this.fingerprint="";}
    setConfig(config){this.config=config||{};}
    set hass(hass){
      this._hass=hass;
      const a=hass.states["sensor.smoobu_mittelhof_workflow_status"]?.attributes||{};
      const fp=JSON.stringify([a.laundry_stock_items,a.laundry_stock_pending_orders,
        a.laundry_stock_pending_deliveries,hass.user?.is_admin]);
      if(fp!==this.fingerprint){this.fingerprint=fp;this.render(a,!!hass.user?.is_admin);}
    }
    async execute(service,data,question){
      if(!this._hass||!confirm(question))return;
      try{
        await this._hass.callService("smoobu_mittelhof",service,data);
        alert("Home Assistant hat die Aktion angenommen. Bitte Bestandsanzeige kontrollieren.");
      }catch(e){alert("HA-Aktion fehlgeschlagen: "+(e?.message||e));}
    }
    render(a,admin){
      const root=this.shadowRoot;root.replaceChildren();
      const css=el("style");
      css.textContent=":host{display:block}.card{background:var(--card-background-color,#fff);color:var(--primary-text-color);padding:16px;border-radius:12px}.tiles,.houses,.fields{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}.tile,.house,.panel{border:1px solid var(--divider-color,#ddd);border-radius:8px;padding:12px}.tile strong{display:block;font-size:26px}.note{color:var(--secondary-text-color);font-size:13px;line-height:1.5}.quantity{display:grid;gap:4px;font-size:13px}input,select{box-sizing:border-box;width:100%;font:inherit;padding:9px;border:1px solid #a9b5aa;border-radius:6px}.fields{grid-template-columns:repeat(2,minmax(0,1fr))}button{width:100%;margin:12px 0 0;padding:11px;border:0;border-radius:6px;background:var(--primary-color,#245c3c);color:white;cursor:pointer}.panel{margin-top:12px}.danger{background:#8e4934}h2{margin:4px 0 14px;font-size:21px}h3{font-size:16px}hr{border:0;border-top:1px solid var(--divider-color,#ddd);margin:24px 0}@media(max-width:460px){.fields{grid-template-columns:1fr}}";
      css.textContent += ".sim-output{background:var(--secondary-background-color,#f4f7f5);margin-top:8px;padding:12px;border-radius:8px}.sim-line{font-size:12px;margin:5px 0}.sim-safe{color:#387350;font-weight:bold;font-size:12px}.sim-error{color:#ae3a37;font-weight:bold;font-size:12px}";
      root.append(css);
      const body=el("div",null,"card");root.append(body);
      body.append(el("h2","Mittelhof · Wäschebestand"));
      body.append(el("p","Ein Set = 1 Kopfkissenbezug, 1 Laken, 1 Bettdeckenbezug, 1 Badetuch, 1 Handtuch. Badvorleger separat.","note"));
      const start=a.laundry_tracking_start_date||"2026-11-01";
      const stock=a.laundry_stock_items;
      if(!stock||keys.some(k=>!Number.isInteger(stock[k]))){
        body.append(el("p","Die Einzelartikel fehlen im HA-Status. Bitte Smoobu Workflow v0.6.0 installieren.","note"));return;
      }
      const tiles=el("div",null,"tiles");body.append(tiles);
      keys.forEach(k=>{
        const t=el("div",null,"tile");t.append(el("span",labels[k]),el("strong",stock[k]));
        if(stock[k]<=(k==="bath_mat"?2:12))t.append(el("span","Mindestbestand erreicht","note"));
        tiles.append(t);
      });
      body.append(el("p","Vollständige Sets möglich: "+Math.min(...keys.slice(0,5).map(k=>stock[k])),"note"));
      body.append(el("h2","Reinigung erfassen"));
      const housegrid=el("div",null,"houses");body.append(housegrid);
      for(const [name,id] of houses){
        const box=el("div",null,"house");housegrid.append(box);
        box.append(el("h3",name));
        const select=el("input");select.type="number";select.min="0";select.max="8";select.step="1";select.value="2";
        const setLabel=el("label",null,"quantity");setLabel.append(el("span","Vollständige Sets (0–8)"),select);
        box.append(setLabel);
        box.append(el("p","Zusätzliche Einzelteile (inkl. Vorleger):","note"));
        const fields=el("div",null,"fields");
        keys.forEach(k=>fields.append(numberField(k,0)));
        box.append(fields);
        const previewButton=el("button","SIMULIEREN – nichts buchen");
        const output=el("div",null,"sim-output");
        previewButton.addEventListener("click",()=>{
          output.replaceChildren();
          try{
            const sets=Number(select.value),extras=read(fields);
            const report=simulation(stock,sets,extras);
            output.append(el("h3","Nur hypothetisch · "+name));
            for(const key of keys)
              output.append(el("p",labels[key]+": "+stock[key]+" - "+report.used[key]+" = "+report.rest[key],"sim-line"));
            output.append(el("p","Danach mögliche vollständige Sets: "+report.possibleSets,"note"));
            if(!report.valid)output.append(el("p","NICHT möglich: zu wenig saubere Artikel. Keine Bestandsänderung.","sim-error"));
            else{
              const proposed=keys.filter(k=>report.reorder[k]>0).map(k=>labels[k]+": "+report.reorder[k]);
              output.append(el("p",proposed.length?
                "Unverbindlicher Bestellvorschlag: "+proposed.join(" · "):
                "Kein Bestellvorschlag nötig.","note"));
            }
            output.append(el("p","Simulation vollständig lokal – keine Buchung, keine Bestellung.","sim-safe"));
          }catch(e){output.append(el("p",e.message,"sim-error"));}
        });
        box.append(previewButton,output);
        box.append(el("p","Produktive Wäschepflege ausschließlich im Mittelhof-Mitarbeiterportal.","note"));
      }
      body.append(el("hr"));
      body.append(el("h2","Portal ist die führende Bedienoberfläche"));
      body.append(el("p","Home Assistant ist die einzige Datenquelle für Smoobu-Buchungen, Bestände, Nachbestellungen und Liefereingänge. Alle echten Aktionen erfolgen im Mitarbeiterportal.","note"));
      const link=el("a","Mittelhof-Mitarbeiterportal öffnen");
      link.href="https://puretraveller.de/intern/";
      link.target="_blank";link.rel="noopener noreferrer";
      body.append(link);
      const orders=Array.isArray(a.laundry_stock_pending_orders)?a.laundry_stock_pending_orders:[];
      const deliveries=Array.isArray(a.laundry_stock_pending_deliveries)?a.laundry_stock_pending_deliveries:[];
      body.append(el("p","Bestellvorschläge in HA: "+orders.length+
        " · Offene Lieferungen: "+deliveries.length+
        " · Offene Wäscheerfassungen: "+Number(a.laundry_consumptions_pending||0),"note"));
    }
    getCardSize(){return 10;}
    static getStubConfig(){return {};}
  }
  customElements.define("mittelhof-laundry-card",MittelhofLaundryCard);
  window.customCards=window.customCards||[];
  window.customCards.push({type:"mittelhof-laundry-card",name:"Mittelhof Wäsche",description:"Einzelartikel, Sets, Bestellvorschläge und Wareneingang"});
})();
