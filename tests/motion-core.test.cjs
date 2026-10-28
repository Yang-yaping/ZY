const {test} = require('node:test');
const assert = require('node:assert/strict');
const {clamp,wheelPixels,WheelIntent} = require('../web/showcase/motion-core.js');

test('one move per trackpad momentum gesture and a new move after quiet',()=>{
  const gate=new WheelIntent();
  assert.equal(gate.observe(12,0),0);
  assert.equal(gate.observe(18,12),0);
  assert.equal(gate.observe(20,24),1);
  for(let t=36;t<1500;t+=12) assert.equal(gate.observe(20,t,t<900),0);
  assert.equal(gate.observe(70,1800),1);
});
test('animation-period wheel events cannot become a queued extra screen',()=>{
  const gate=new WheelIntent();
  assert.equal(gate.observe(120,0),1);
  assert.equal(gate.observe(100,850,true),0);
  assert.equal(gate.observe(100,920),0);
  assert.equal(gate.observe(-100,1250),-1);
});
test('direction reversal resets accumulated delta and bounds prevent wrapping',()=>{
  const gate=new WheelIntent();
  assert.equal(gate.observe(30,0),0);
  assert.equal(gate.observe(-20,20),0);
  assert.equal(gate.observe(-30,40),-1);
  assert.equal(clamp(-1,0,3),0);
  assert.equal(clamp(9,0,3),3);
});
test('wheel line and page units normalize without treating horizontal motion as vertical',()=>{
  assert.deepEqual(wheelPixels({deltaX:0,deltaY:3,deltaMode:1}),{x:0,y:48});
  assert.deepEqual(wheelPixels({deltaX:2,deltaY:0,deltaMode:2},600),{x:1200,y:0});
});
