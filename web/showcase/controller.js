/* One transition path for navigation, wheel, touch, keyboard and controls. */
(function () {
  'use strict';
  const config = JSON.parse(document.getElementById('scene-config').textContent);
  const { clamp, wheelPixels, WheelIntent } = window.YinbiMotion;
  const stage = document.getElementById('stage');
  const list = document.getElementById('scene-list');
  const loading = document.getElementById('loading');
  const announcement = document.getElementById('announcement');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const wheelIntent = new WheelIntent();
  const animated = new Set();
  let current = clamp(config.initial || 0, 0, config.scenes.length - 1);
  let busy = false;
  let pending = null;
  let navigationTarget = current;
  let touch = null;
  let live = true;
  const scenes = config.scenes.map((scene, index) => {
    const section = document.createElement('section');
    section.className = 'scene';
    section.setAttribute('aria-label', scene.title);
    section.setAttribute('aria-roledescription', '全屏页面');
    section.dataset.scene = scene.id;
    const visual = document.createElement('div');
    visual.className = 'scene__visual';
    const img = new Image(scene.width, scene.height);
    img.className = 'scene__image';
    img.alt = scene.alt;
    img.decoding = 'async';
    img.fetchPriority = index === current ? 'high' : 'low';
    img.src = config.assetRoot + scene.file;
    visual.append(img);
    section.append(visual);
    const shade = document.createElement('div');
    shade.className = 'scene__shade';
    section.append(shade);
    const foreground = document.createElement('div');
    foreground.className = 'scene__foreground';
    const mobile = document.createElement('div');
    mobile.className = 'mobile-copy';
    const kicker = document.createElement('p'); kicker.className = 'kicker'; kicker.textContent = scene.eyebrow;
    const title = document.createElement('h1'); title.textContent = scene.heading;
    const description = document.createElement('p'); description.textContent = scene.description;
    mobile.append(kicker, title, description);
    if (index === 3) {
      const note = document.createElement('p'); note.className = 'mobile-status';
      note.textContent = '问题001、002、003… · 左侧题目，右侧答案'; mobile.append(note);
    }
    foreground.append(mobile);
    const actions = document.createElement('div'); actions.className = 'scene__actions';
    const link = document.createElement('a');
    link.className = 'scene__action'; link.href = scene.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.textContent = scene.action + ' ↗';
    const original = document.createElement('button'); original.className = 'scene__original';
    original.textContent = '查看完整原图'; original.addEventListener('click', () => openImage(index));
    actions.append(link, original); foreground.append(actions);
    // Make the principal action already drawn in each original design useful.
    const hitplane = document.createElement('div'); hitplane.className = 'design-hitplane';
    // Apply the approved wording as HTML; keep the original raster file intact.
    if (scene.id === 'home') {
      const courseLabel = document.createElement('div'); courseLabel.className = 'home-course-label';
      const heading = document.createElement('span'); heading.textContent = '课程作业';
      const caption = document.createElement('small'); caption.textContent = '教师题目 · 我的回答';
      courseLabel.append(heading, caption); hitplane.append(courseLabel);
    }
    for (const hotspot of scene.hotspots || []) {
      const hit = document.createElement(hotspot.goto === undefined ? 'a' : 'button');
      hit.className = 'scene__hotspot';
      hit.style.cssText = `left:${hotspot.x}%;top:${hotspot.y}%;width:${hotspot.w}%;height:${hotspot.h}%;`;
      hit.setAttribute('aria-label', hotspot.label);
      if (hotspot.goto !== undefined) hit.addEventListener('click', () => transitionTo(hotspot.goto, 'nav'));
      else { hit.href = scene.href; hit.target = '_blank'; hit.rel = 'noopener noreferrer'; }
      hitplane.append(hit);
    }
    foreground.append(hitplane); section.append(foreground); list.append(section);
    return { section, visual, foreground, img, data: scene };
  });

  const nextFrame = () => new Promise(resolve => requestAnimationFrame(resolve));
  const safeDecode = async (img) => {
    if (!img.complete) {
      await new Promise((resolve, reject) => {
        img.addEventListener('load', resolve, { once: true });
        img.addEventListener('error', () => reject(new Error('图片未能载入')), { once: true });
      });
    }
    if (!img.naturalWidth) throw new Error('图片未能载入');
    if (img.decode) { try { await img.decode(); } catch (_) { /* Already loaded PNG remains usable. */ } }
  };
  function activeNavigation(index) {
    navigationTarget = index;
    document.querySelectorAll('[data-goto]').forEach(button => {
      if (Number(button.dataset.goto) === index) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    const tab = document.querySelector(`.main-nav [data-goto="${index}"]`);
    const underline = document.querySelector('.nav-underline');
    underline.style.width = tab.offsetWidth + 'px';
    underline.style.transform = `translateX(${tab.offsetLeft}px)`;
    document.getElementById('screen-number').textContent = String(index + 1).padStart(2, '0');
    document.getElementById('previous').disabled = index === 0;
    document.getElementById('next').disabled = index === scenes.length - 1;
    document.getElementById('scroll-label').textContent = index === scenes.length - 1 ? '向上回看' : '滚动探索';
    const action = document.getElementById('nav-action');
    action.href = scenes[index].data.href;
    action.setAttribute('aria-label', scenes[index].data.action);
    action.firstChild.textContent = index === 3 ? '查看作业 ' : '进入实验 ';
  }
  function settle(index) {
    scenes.forEach((scene, n) => {
      scene.section.classList.toggle('is-active', n === index);
      scene.section.classList.remove('is-transitioning');
      scene.section.style.removeProperty('z-index');
      scene.section.inert = n !== index;
      scene.section.setAttribute('aria-hidden', String(n !== index));
    });
    stage.dataset.currentIndex = String(index);
    stage.dataset.currentScene = scenes[index].data.id;
    activeNavigation(index);
  }
  function animate(element, frames, timing) {
    const animation = element.animate(frames, timing);
    animated.add(animation);
    return animation;
  }
  async function transitionTo(requested, source = 'nav') {
    if (!Number.isInteger(requested)) return;
    const target = clamp(requested, 0, scenes.length - 1);
    if (busy) { if (source === 'nav') pending = target; return; }
    if (target === current || !live) return;
    busy = true; stage.dataset.transitioning = 'true'; stage.setAttribute('aria-busy', 'true');
    const from = scenes[current]; const to = scenes[target];
    let moving = [];
    try {
      // The old screen stays visible while the incoming image is decoded.
      if (!to.img.complete || !to.img.naturalWidth) loading.hidden = false;
      await safeDecode(to.img);
      if (!live) return;
      loading.hidden = true;
      const direction = Math.sign(target - current);
      const duration = reducedMotion.matches ? 0 : 880;
      const timing = { duration, easing: 'cubic-bezier(.65,0,.35,1)', fill: 'both' };
      from.section.classList.add('is-transitioning');
      from.section.inert = true;
      to.section.classList.add('is-transitioning');
      from.section.style.zIndex = '1'; to.section.style.zIndex = '2';
      to.section.inert = true;
      await nextFrame();
      moving = [
        animate(from.section, [
          { transform: 'translate3d(0,0,0) scale(1)', opacity: 1 },
          { transform: `translate3d(0,${-direction * 9}%, -70px) scale(.955) rotateX(${direction * .8}deg)`, opacity: .16 }
        ], timing),
        animate(to.section, [
          { transform: `translate3d(0,${direction * 101}%,0) scale(1.025)`, opacity: 1 },
          { transform: 'translate3d(0,0,0) scale(1)', opacity: 1 }
        ], timing),
        animate(to.visual, [
          { transform: `translate3d(0,${-direction * 3.5}%,0) scale(1.035)` },
          { transform: 'translate3d(0,0,0) scale(1)' }
        ], timing),
        animate(to.foreground, [
          { transform: `translate3d(0,${direction * 3}%,0)`, opacity: .2 },
          { transform: 'translate3d(0,0,0)', opacity: 1 }
        ], timing)
      ];
      // The navbar travels on the same clock and curve as the scene transition.
      activeNavigation(target);
      await Promise.all(moving.map(a => a.finished));
      current = target;
      settle(current);
      announcement.textContent = `第${current + 1}屏，共4屏：${scenes[current].data.title}`;
    } catch (error) {
      if (live) {
        settle(current);
        announcement.textContent = '页面图片暂未载入，请稍后重试。';
        loading.textContent = '图片载入失败，请检查连接后再切换'; loading.hidden = false;
      }
    } finally {
      moving.forEach(a => { a.cancel(); animated.delete(a); });
      busy = false; stage.dataset.transitioning = 'false'; stage.setAttribute('aria-busy', 'false');
      if (live && pending !== null) {
        const next = pending; pending = null;
        if (next !== current) void transitionTo(next, 'nav');
      }
    }
  }
  function ignoresInput(target) {
    return document.getElementById('image-dialog').open ||
      !!target.closest('input,textarea,select,[contenteditable="true"],[data-native-scroll]');
  }
  document.querySelectorAll('[data-goto]').forEach(button => {
    button.addEventListener('click', () => transitionTo(Number(button.dataset.goto), 'nav'));
  });
  document.getElementById('previous').addEventListener('click', () => transitionTo(current - 1, 'nav'));
  document.getElementById('next').addEventListener('click', () => transitionTo(current + 1, 'nav'));
  window.addEventListener('wheel', event => {
    if (event.ctrlKey || event.metaKey || ignoresInput(event.target)) return;
    const { x, y } = wheelPixels(event, innerHeight);
    if (Math.abs(x) > Math.abs(y) || !y) return;
    event.preventDefault();
    const direction = wheelIntent.observe(y, performance.now(), busy);
    if (direction) void transitionTo(current + direction, 'wheel');
  }, { passive: false });
  window.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.repeat || ignoresInput(event.target)) return;
    if (event.key === ' ' && event.target.closest('button,a')) return;
    let target;
    if (['ArrowDown', 'PageDown', 'ArrowRight'].includes(event.key) || (event.key === ' ' && !event.shiftKey)) target = current + 1;
    if (['ArrowUp', 'PageUp', 'ArrowLeft'].includes(event.key) || (event.key === ' ' && event.shiftKey)) target = current - 1;
    if (event.key === 'Home') target = 0;
    if (event.key === 'End') target = scenes.length - 1;
    if (target !== undefined) { event.preventDefault(); if (!busy) void transitionTo(target, 'keyboard'); }
  });
  stage.addEventListener('touchstart', event => {
    if (event.touches.length !== 1 || ignoresInput(event.target)) { touch = null; return; }
    const point = event.touches[0]; touch = { x: point.clientX, y: point.clientY, at: performance.now(), blocked: busy };
  }, { passive: true });
  stage.addEventListener('touchmove', event => {
    if (!touch || event.touches.length !== 1 || ignoresInput(event.target)) return;
    const point = event.touches[0];
    if (Math.abs(point.clientY - touch.y) > Math.abs(point.clientX - touch.x)) event.preventDefault();
  }, { passive: false });
  stage.addEventListener('touchend', event => {
    if (!touch || !event.changedTouches.length) return;
    const origin = touch; touch = null;
    const point = event.changedTouches[0];
    const dx = point.clientX - origin.x; const dy = point.clientY - origin.y;
    if (origin.blocked || busy || performance.now() - origin.at > 1200 || Math.abs(dy) < 46 || Math.abs(dy) < Math.abs(dx) * 1.1) return;
    void transitionTo(current + (dy < 0 ? 1 : -1), 'touch');
  }, { passive: true });
  stage.addEventListener('touchcancel', () => { touch = null; }, { passive: true });
  const dialog = document.getElementById('image-dialog');
  function openImage(index) {
    const image = document.getElementById('full-image'); image.src = scenes[index].img.src;
    image.alt = scenes[index].data.alt;
    document.getElementById('image-dialog-title').textContent = scenes[index].data.title + ' · 原图';
    dialog.showModal();
  }
  document.getElementById('close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  reducedMotion.addEventListener('change', () => {
    if (reducedMotion.matches) animated.forEach(a => { try { a.finish(); } catch (_) { /* Already finished. */ } });
  });
  window.addEventListener('resize', () => activeNavigation(navigationTarget));
  window.addEventListener('pagehide', () => { live = false; animated.forEach(a => a.cancel()); });
  settle(current);
  stage.dataset.transitioning = 'false';
  safeDecode(scenes[current].img).then(() => {
    loading.hidden = true; stage.dataset.ready = 'true';
    // Hovering over the full-screen iframe and keyboard navigation share focus.
    stage.focus({ preventScroll: true });
  }).catch(() => { loading.textContent = '图片载入失败，请刷新页面'; });
  if (document.fonts?.ready) document.fonts.ready.then(() => activeNavigation(current));
})();
