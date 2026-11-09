"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
class HTMLElement {
  constructor(){this.shadowRoot={querySelector:()=>null};}
  attachShadow(){return this.shadowRoot;}
}
const customElements={get:()=>false,define(){}};
const code=fs.readFileSync(path.join(__dirname,"../custom_components/smoobu_mittelhof/frontend/mittelhof-accounting-card.js"),"utf8");
const Card=vm.runInNewContext(code+"\nMittelhofAccountingCard;",{HTMLElement,customElements,Date,console});
async function run(){
  const card=new Card();
  card._hass={callApi:async(method,endpoint)=>{
    assert.equal(method,"POST");
    assert.equal(endpoint,"smoobu_mittelhof/guest/v1/bookings/12345/accounting");
    throw {status:404,message:"response error 404"};
  }};
  await assert.rejects(card._api("POST","bookings/12345/accounting",{confirm_tax_review:true}),error=>{
    assert.match(error.message,/HTTP 404 bei POST/);
    assert.match(error.message,/bookings\/\{id\}\/accounting/);
    assert.doesNotMatch(error.message,/12345/);
    assert.doesNotMatch(error.message,/\[object Object\]/);
    return true;
  });
  card._hass={callApi:async()=>({record:{status:"ready"}})};
  const success=await card._api("POST","bookings/12345/accounting",{});
  assert.equal(success.record.status,"ready");
  card._hass={callApi:async()=>{throw {status:409,message:{message:"Smoobu-Betrag stimmt nicht überein"}};}};
  await assert.rejects(card._api("POST","bookings/12345/accounting",{}),error=>{
    assert.match(error.message,/HTTP 409/);
    assert.match(error.message,/Smoobu-Betrag stimmt nicht überein/);
    return true;
  });
  console.log("Accounting API 404 route diagnostics: OK");
}
run().catch(error=>{console.error(error);process.exitCode=1;});
