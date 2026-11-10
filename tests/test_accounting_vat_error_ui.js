/* Offline UI regression for VAT default and error diagnostics. */
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
class HTMLElement {
  constructor() {this.shadowRoot={querySelector:()=>null,querySelectorAll:()=>[]};}
  attachShadow(){return this.shadowRoot;}
}
const customElements={get:()=>false,define(){}};
const src=fs.readFileSync(path.join(__dirname,
"../custom_components/smoobu_mittelhof/frontend/mittelhof-accounting-card.js"),"utf8");
const Card=vm.runInNewContext(src+"\nMittelhofAccountingCard;",{
  HTMLElement,customElements,Date,console
});
const testError=Card.errorText({status:409,message:{message:"Quellbuchung geändert"}});
assert.equal(testError,"HTTP 409: Quellbuchung geändert");
assert.equal(Card.errorText({message:{error:"Freigabe nicht möglich"}}),"Freigabe nicht möglich");
assert.equal(Card.errorText({message:"Umsatzsteuer ungültig"}),"Umsatzsteuer ungültig");
assert.doesNotMatch(Card.errorText({message:{meta:{x:2}}}),/\[object Object\]/);

const card=new Card();
let html="";
card.shadowRoot={
  set innerHTML(value){html=value;},
  get innerHTML(){return html;},
  querySelector:()=>null,
  querySelectorAll:()=>[]
};
card._selected={
  source:{
    booking_id:"98765",guest:"Test Gast",house:"Haus 14",channel:"Airbnb",
    total_gross:"475.00",arrival:"2026-12-22",departure:"2026-12-27",
    accounting_type:"Einnahme", document_number:"98765", service_date:"2026-12-27",
    booking_created_at:"2026-11-09", document_date:"2026-11-09", due_date:"2026-12-23",
    rows:[
      {source_index:0,description:"Base Price",gross:"355.00",quantity:1},
      {source_index:1,description:"Cleaning fee",gross:"55.00",quantity:1},
      {source_index:2,description:"PASS_THROUGH_PET_FEE",gross:"35.00",quantity:1},
      {source_index:3,description:"Additional Guest Fee",gross:"30.00",quantity:1},
    ],
    warnings:[],ignored_settlement_lines:[],
  },
  record:null,source_changed:false,
};
card._render();
assert.match(html,/Belegdatum:<\/strong> 2026-11-09/);
assert.match(html,/Belegnummer:<\/strong> 98765/);
assert.match(html,/Leistungsdatum:<\/strong> 2026-12-27/);
assert.match(html,/Belegtyp:<\/strong> Einnahme/);
assert.match(html,/Fälligkeitsdatum:<\/strong> 2026-12-23/);
assert.match(html,/geplantes Zahlungsziel nach Mittelhof-Buchungskanalregel/);
const selects=html.match(/<select data-rate[^>]*>[\s\S]*?<\/select>/g)||[];
assert.equal(selects.length,4);
for(const select of selects){
  assert.match(select,/<option value="7" selected>7 %<\/option>/);
  assert.doesNotMatch(select,/<option value="19" selected>/);
}
card._selected.record={status:"ready",reviewed_rows:[{source_index:0,
    tax_rate:"19",description:"Base Price",gross:"355.00"}]};
card._render();
const updated=(html.match(/<select data-rate[^>]*>[\s\S]*?<\/select>/g)||[]);
assert.match(updated[0],/<option value="19" selected>19 %<\/option>/);
assert.match(updated[1],/<option value="7" selected>7 %<\/option>/);

card._error=Card.errorText({message:{message:"Positionensumme ist ungültig"}});
card._render();
assert.match(html,/Positionensumme ist ungültig/);
assert.doesNotMatch(html,/\[object Object\]/);

console.log("Accounting VAT 7% defaults / error diagnostics regression: OK");
