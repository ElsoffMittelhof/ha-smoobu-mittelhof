/* Mittelhof v0.6 – HA-only warehouse card; no external network access. */
(() => {
  const labels={pillowcase:"Kopfkissenbezüge",flat_sheet:"Laken",fitted_sheet:"Spannbetttücher",
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
      root.append(css);
      const body=el("div",null,"card");root.append(body);
      body.append(el("h2","Mittelhof · Wäschebestand"));
      body.append(el("p","Ein Set = 1 Kopfkissenbezug, 1 Laken, 1 Spannbetttuch, 1 Badetuch, 1 Handtuch. Badvorleger separat.","note"));
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
        const select=el("select");
        for(const [n,label] of [[0,"Nur einzelne Artikel"],[2,"2 Sets"],[4,"4 Sets"]]){
          const opt=el("option",label);opt.value=String(n);select.append(opt);
        }
        select.value="2";box.append(select);
        box.append(el("p","Zusätzliche Einzelteile (inkl. Vorleger):","note"));
        const fields=el("div",null,"fields");
        keys.forEach(k=>fields.append(numberField(k,0)));
        box.append(fields);
        const btn=el("button","Verbrauch bestätigen");
        btn.addEventListener("click",()=>{
          try{
            const sets=Number(select.value),items=read(fields);
            if(sets===0&&!Object.values(items).some(v=>v>0))throw Error("Kein Wäscheverbrauch eingetragen.");
            this.execute("record_laundry_consumption",{apartment_id:id,sets,items},
              "Diesen Verbrauch für "+name+" wirklich abbuchen?");
          }catch(e){alert(e.message);}
        });
        box.append(btn);
      }
      if(!admin)return;
      body.append(el("hr"));
      body.append(el("h2","Admin · Bestellungen und Wareneingang"));
      const orders=Array.isArray(a.laundry_stock_pending_orders)?a.laundry_stock_pending_orders:[];
      const deliveries=Array.isArray(a.laundry_stock_pending_deliveries)?a.laundry_stock_pending_deliveries:[];
      if(!orders.length&&!deliveries.length)body.append(el("p","Keine offene Bestellung oder Lieferung.","note"));
      for(const order of orders){
        const panel=el("div",null,"panel");body.append(panel);
        panel.append(el("h3","Bestellvorschlag"));
        panel.append(el("p",keys.filter(k=>order.items?.[k]).map(k=>labels[k]+": "+order.items[k]).join(" · ")));
        const btn=el("button","Bestell-E-Mail freigeben","danger");
        btn.addEventListener("click",()=>this.execute("laundry_command",{command:"send",request_id:order.id},
          "Bestellung wirklich per E-Mail versenden? Lager wird erst bei Lieferung erhöht."));
        panel.append(btn);
      }
      for(const delivery of deliveries){
        const panel=el("div",null,"panel");body.append(panel);
        panel.append(el("h3","Lieferung: "+String(delivery.id)));
        panel.append(el("p","Nur wirklich eingetroffene Mengen eingeben.","note"));
        const fields=el("div",null,"fields");panel.append(fields);
        keys.forEach(k=>{
          const remaining=Math.max(0,Number(delivery.items?.[k]||0)-Number(delivery.received_items?.[k]||0));
          fields.append(numberField(k,remaining,remaining));
        });
        const btn=el("button","Wareneingang buchen");
        btn.addEventListener("click",()=>{
          try{
            const items=read(fields);
            if(!Object.values(items).some(v=>v>0))throw Error("Keine Stücke erhalten.");
            this.execute("receive_laundry_delivery",{request_id:delivery.id,items},
              "Diese tatsächlich gelieferten Teile zum verfügbaren Lager addieren?");
          }catch(e){alert(e.message);}
        });
        panel.append(btn);
      }
      body.append(el("hr"));
      const panel=el("div",null,"panel");body.append(panel);
      panel.append(el("h3","Physische Inventur (nur Admin)"));
      panel.append(el("p","Die Zählwerte ersetzen die verfügbaren Artikelbestände; die Buchungshistorie bleibt erhalten.","note"));
      const fields=el("div",null,"fields");panel.append(fields);
      keys.forEach(k=>fields.append(numberField(k,stock[k],10000)));
      const btn=el("button","Inventurkorrektur speichern","danger");
      btn.addEventListener("click",()=>{
        try{this.execute("reconcile_laundry_items",{items:read(fields)},
          "Alle sechs Lagerbestände tatsächlich überschreiben? Nicht für Tests verwenden.");}
        catch(e){alert(e.message);}
      });
      panel.append(btn);
    }
    getCardSize(){return 10;}
    static getStubConfig(){return {};}
  }
  customElements.define("mittelhof-laundry-card",MittelhofLaundryCard);
  window.customCards=window.customCards||[];
  window.customCards.push({type:"mittelhof-laundry-card",name:"Mittelhof Wäsche",description:"Einzelartikel, Sets, Bestellvorschläge und Wareneingang"});
})();
