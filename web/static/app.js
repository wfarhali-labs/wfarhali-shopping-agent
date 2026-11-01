/* Wfarhali Agent: one page. Sends each turn (text, voice as WAV, photo) to /api/turn and renders
 * the agent's steps, its question or its proposal. All model/provider text is inserted with textContent. */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const chat = $('#chat'), form = $('#composer'), input = $('#text');
  const photoInput = $('#photoInput'), photoChip = $('#photoChip'), mic = $('#micBtn');
  const EMOJI = { shoes: '👟', fashion: '👗', bag: '👜', jewelry: '⌚', beauty: '🧴', electronics: '🎧' };
  const dzd = (n) => `≈ ${new Intl.NumberFormat('fr-FR').format(n)} دج`;
  let sessionId = '', photo = null, busy = false, whatsapp = '', understanding = null;

  fetch('/api/health').then((r) => r.json()).then((h) => { whatsapp = h.whatsapp || ''; $('#mode').textContent = `${h.model} · ${h.catalogue} · ${h.speech}`; }).catch(() => {});

  // The confirmed basket goes to Wfarhali's team as a WhatsApp message the customer sends themself (nothing touches the website).
  function whatsappMessage(p) {
    const lines = ['سلام وفرهالي 👋 حاب نأكد طلب السعر لهذه السلة (من وكيل وفرهالي):'];
    p.items.forEach((item, i) => {
      lines.push(`${i + 1}. ${item.title} — ${item.store || ''} — ${item.price_dzd ? '≈ ' + item.price_dzd + ' دج' : 'السعر يتأكد'}`);
      if (item.product_url) lines.push(item.product_url);
    });
    lines.push(`المجموع التقديري: ${p.total_dzd} دج${p.budget_dzd ? ' / ميزانيتي: ' + p.budget_dzd + ' دج' : ''}`);
    const u = understanding || {};
    if (u.wilaya) lines.push(`الولاية: ${u.wilaya}`);
    const sizes = (u.items || []).filter((it) => it.size || it.color).map((it) => `${it.need}: ${[it.size && 'مقاس ' + it.size, it.color].filter(Boolean).join(', ')}`);
    if (sizes.length) lines.push(`التفاصيل: ${sizes.join(' | ')}`);
    return lines.join('\n');
  }

  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const bilingual = (ar, en, cls = 'p') => { const p = el(cls); p.append(document.createTextNode(ar || '')); if (en) p.append(el('span', 'en', en)); return p; };
  const scroll = () => { chat.scrollTop = chat.scrollHeight; };

  function addUser(text, photoUrl) {
    $('#hello')?.remove();
    const node = $('#tplUser').content.firstElementChild.cloneNode(true);
    $('p', node).textContent = text || '📷';
    if (photoUrl) { const img = $('img', node); img.src = photoUrl; img.hidden = false; }
    chat.querySelectorAll('.msg.user .edit').forEach((b) => b.remove());          // only the last message can be edited
    const edit = $('.edit', node);
    if (text && !text.startsWith('🎤') && !text.startsWith('بدّل')) {
      edit.addEventListener('click', () => { input.value = text; input.focus(); });
    } else { edit.remove(); }
    chat.append(node); scroll();
  }

  // "Start over": a new conversation, nothing of the old one is kept on the server side either (new session id).
  $('#newChat').addEventListener('click', () => {
    sessionId = ''; understanding = null; clearPhoto(); input.value = '';
    chat.replaceChildren(helloNode.cloneNode(true));
    chat.querySelectorAll('[data-example]').forEach((b) => b.addEventListener('click', () => send({ text: b.dataset.example })));
    input.focus();
  });
  const helloNode = $('#hello').cloneNode(true);

  const HINTS = [['…يفهم طلبك', 'understanding…'], ['…يبحث في متاجر العالم (ياخذ ثواني)', 'searching world stores (takes a few seconds)…'],
                 ['…يحسب السلة في حدود الميزانية', 'planning within budget…'], ['…يحضّر الاقتراح', 'preparing the proposal…']];
  function stepsBox() {
    const node = $('#tplSteps').content.firstElementChild.cloneNode(true);
    const li = el('li', 'busy'); li.append(bilingual(HINTS[0][0], HINTS[0][1], 'span'));
    const clock = el('span', 'clock', '0 ث'); li.append(clock);
    $('ol', node).append(li); chat.append(node); scroll();
    const started = Date.now();
    node._timer = setInterval(() => {                       // live feedback while the agent works
      const s = Math.round((Date.now() - started) / 1000);
      clock.textContent = `${s} ث · ${s}s`;
      const hint = HINTS[Math.min(HINTS.length - 1, Math.floor(s / 4))];
      li.firstChild.replaceWith(bilingual(hint[0], hint[1], 'span'));
    }, 1000);
    return node;
  }

  function renderSteps(box, steps) {
    const list = $('ol', box); list.replaceChildren();
    steps.filter((s) => s.tool !== 'propose_basket' && s.tool !== 'ask_customer').forEach((s) => {
      const li = el('li', s.ok ? '' : 'fail');
      const d = s.detail || {};
      let ar = s.label_darija, en = s.label_en;
      if (s.tool === 'record_understanding' && d.summary_darija) { ar = `فهمت: ${d.summary_darija}`; en = `Understood: ${d.summary_en}`; }
      if (s.tool === 'search_catalogue' && d.query) { ar = `${s.label_darija}: ${d.need} — ${d.count} منتج`; en = `${s.label_en}: “${d.query}” — ${d.count} products`; }
      if (s.tool === 'locate_in_photo' && d.count != null) {
        ar = d.count === 1 ? `${s.label_darija}: ${d.need} — هذا هو لي فهمت` : d.count === 0 ? `ما لقيتش «${d.need}» في الصورة` : `لقيت ${d.count} «${d.need}» في الصورة`;
        en = `${s.label_en}: “${d.need}” — ${d.count} match${d.count === 1 ? '' : 'es'}`;
      }
      if (s.tool === 'plan_basket' && d.total_dzd != null) { ar = `${s.label_darija}: ${dzd(d.total_dzd)}`; en = `${s.label_en}: ${d.within_budget ? 'fits' : 'over by ' + d.over_by_dzd + ' DZD'}`; }
      if (!s.ok) { en = `${s.label_en} — retried`; }
      const body = el('div'); body.append(bilingual(ar, en, 'span'));
      if (d.thumbnails?.length) { const t = el('div', 'thumbs'); d.thumbnails.forEach((u) => { const i = el('img'); i.src = u; i.alt = ''; i.referrerPolicy = 'no-referrer'; t.append(i); }); body.append(t); }
      li.append(body); list.append(li);
    });
  }

  function renderQuestion(q) {
    const node = el('div', 'msg agent'); node.append(bilingual(q.question_darija, q.question_en));
    if (q.options?.length) {                                   // tap an answer instead of typing it
      const row = el('div', 'options');
      q.options.forEach((o) => {
        const b = el('button', 'option', o); b.type = 'button';
        b.addEventListener('click', () => { row.querySelectorAll('button').forEach((x) => { x.disabled = true; }); send({ text: o }); });
        row.append(b);
      });
      node.append(row);
    }
    chat.append(node); scroll(); input.focus();
  }

  function renderProposal(p) {
    const node = el('div', 'msg agent');
    node.append(bilingual(p.message_darija, p.message_en));
    const cards = el('div', 'cards');
    p.items.forEach((item) => {
      const card = $('#tplCard').content.firstElementChild.cloneNode(true);
      const media = $('.media', card);
      if (item.image_url) { const i = el('img'); i.src = item.image_url; i.alt = item.title; i.referrerPolicy = 'no-referrer'; media.append(i); } else { media.textContent = EMOJI[item.category] || '🛍️'; }
      $('.need', card).textContent = item.need;
      $('h3', card).textContent = item.title;
      $('.store', card).textContent = item.store || 'Store';
      $('.price', card).textContent = item.price_dzd ? dzd(item.price_dzd) : 'السعر في الخطوة الجاية';
      const swap = el('button', 'swap', 'بدّل · Swap');
      swap.type = 'button';
      swap.addEventListener('click', () => {
        node.querySelectorAll('button').forEach((b) => { b.disabled = true; });
        send({ text: `بدّل ${item.need}: ماشي «${item.title}» (id ${item.id})، اقترح لي منتج آخر لنفس الحاجة في نفس الميزانية.`,
               label: `بدّل: ${item.title}` });
      });
      $('.body', card).append(swap);
      cards.append(card);
    });
    node.append(cards);
    const total = el('div', p.within_budget ? 'total' : 'total over');
    const budget = p.budget_dzd ? ` / ${new Intl.NumberFormat('fr-FR').format(p.budget_dzd)} دج` : '';
    total.append(bilingual(`المجموع ${dzd(p.total_dzd)}${budget} — ${p.within_budget ? 'داخل الميزانية ✓' : 'يفوت الميزانية'}`,
      `Total ${p.total_dzd} DZD — ${p.within_budget ? 'within budget ✓' : 'over budget by ' + p.over_by_dzd + ' DZD'}`, 'span'));
    node.append(total);
    node.append(bilingual(p.note_darija, p.note_en, 'p')); node.lastChild.className = 'note';
    const actions = el('div', 'actions');
    const confirm = el('button', 'btn', 'أكّد وأرسل طلب السعر · Confirm');
    confirm.type = 'button';
    confirm.addEventListener('click', () => {
      confirm.disabled = true;
      const done = el('div', 'msg agent');
      if (whatsapp) {
        const url = `https://wa.me/${whatsapp}?text=${encodeURIComponent(whatsappMessage(p))}`;
        window.open(url, '_blank', 'noopener');
        done.append(bilingual('فتحت لك واتساب وفّرهالي والرسالة جاهزة فيها السلة. ابعثها، وفريقنا يأكد لك السعر النهائي.',
          'WhatsApp is open with your basket ready to send. Wfarhali’s team confirms the final price.'));
        const again = el('a', 'en', 'إذا ما تفتحش واتساب، اضغط هنا · Open WhatsApp'); again.href = url; again.target = '_blank'; again.rel = 'noopener';
        done.append(again);
      } else {
        done.append(bilingual('تمام! (عرض تجريبي: ما تبعث حتى طلب). في النسخة الكاملة يوصل الطلب لفريق وفّرهالي ويأكد السعر.',
          'Done! (Demo: nothing was sent.) In the full version the request reaches Wfarhali’s team, who confirm the price.'));
      }
      chat.append(done); scroll();
    });
    actions.append(confirm);
    node.append(actions);
    chat.append(node); scroll();
  }

  async function send({ text = '', audio = null, label = '' } = {}) {
    if (busy) return;
    const usedPhoto = photo;
    if (!text && !audio && !usedPhoto) return;
    busy = true;
    addUser(audio ? '🎤 …' : (label || text), usedPhoto ? usedPhoto.url : null);
    const userBubble = chat.lastElementChild;
    clearPhoto(); input.value = '';
    const box = stepsBox();
    const body = new FormData();
    body.append('text', text); body.append('session_id', sessionId);
    if (audio) body.append('audio', audio, 'voice.wav');
    if (usedPhoto) body.append('image', usedPhoto.file, usedPhoto.file.name || 'photo.jpg');
    try {
      const response = await fetch('/api/turn', { method: 'POST', body });
      const data = await response.json().catch(() => ({}));
      if (data.transcript) $('p', userBubble).textContent = `🎤 ${data.transcript}`;
      if (!response.ok || data.status === 'error') throw new Error(data.error || data.detail || response.statusText);
      sessionId = data.session_id;
      if (data.understanding) understanding = data.understanding;
      renderSteps(box, data.steps || []);
      if (data.status === 'question') renderQuestion(data.question);
      if (data.status === 'proposal') renderProposal(data.proposal);
    } catch (error) {
      const msg = String(error.message || error);
      const darija = msg.includes('silent recording') ? 'التسجيل فارغ: الميكروفون ما سجّل والو. شوفي إذن الميكروفون وعاودي.'
        : msg.includes('nothing understood') ? 'ما فهمتش كلام في التسجيل. عاودي قريب من الميكروفون وبصوت واضح.'
        : msg.includes('too many requests') ? 'بزاف طلبات دروك. عاود جرّب بعد شوية.'
        : 'ما قدرتش نكمّل، عاود جرّب.';
      $('ol', box).replaceChildren(bilingual(darija, msg, 'li'));
      $('ol', box).firstChild.className = 'fail';
    } finally { clearInterval(box._timer); busy = false; scroll(); }
  }

  form.addEventListener('submit', (e) => { e.preventDefault(); send({ text: input.value.trim() }); });
  document.querySelectorAll('[data-example]').forEach((b) => b.addEventListener('click', () => send({ text: b.dataset.example })));

  // ---- photo ----
  function clearPhoto() { photo = null; photoChip.hidden = true; $('#photoThumb').removeAttribute('src'); }
  $('#photoBtn').addEventListener('click', () => photoInput.click());
  $('#photoRemove').addEventListener('click', clearPhoto);
  photoInput.addEventListener('change', () => {
    const file = photoInput.files[0]; photoInput.value = '';
    if (!file) return;
    if (file.size > 6 * 1024 * 1024) { alert('الصورة كبيرة بزاف (6 MB max)'); return; }
    const reader = new FileReader();
    reader.onload = () => { photo = { file, url: String(reader.result) }; $('#photoThumb').src = photo.url; photoChip.hidden = false; };
    reader.readAsDataURL(file);
  });

  // ---- voice: record, convert to mono 16-bit 24 kHz WAV in the browser (Muse Voice Transcribe input) ----
  let recorder = null, chunks = [];
  function wav(buffer) {
    const rate = 24000, data = buffer.getChannelData(0), ratio = buffer.sampleRate / rate;
    const length = Math.floor(data.length / ratio), out = new DataView(new ArrayBuffer(44 + length * 2));
    const str = (o, s) => [...s].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
    str(0, 'RIFF'); out.setUint32(4, 36 + length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
    out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true); out.setUint32(24, rate, true);
    out.setUint32(28, rate * 2, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true); str(36, 'data'); out.setUint32(40, length * 2, true);
    for (let i = 0; i < length; i += 1) { const s = Math.max(-1, Math.min(1, data[Math.floor(i * ratio)])); out.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true); }
    return new Blob([out], { type: 'audio/wav' });
  }
  // A voice note recorded elsewhere (WhatsApp, the phone's recorder…) is decoded by the browser and sent as the same WAV.
  const audioInput = $('#audioInput');
  $('#audioBtn').addEventListener('click', () => audioInput.click());
  audioInput.addEventListener('change', async () => {
    const file = audioInput.files[0]; audioInput.value = '';
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) { alert('الملف كبير بزاف (15 MB max)'); return; }
    try {
      const decoded = await new AudioContext().decodeAudioData(await file.arrayBuffer());
      send({ text: input.value.trim(), audio: wav(decoded) });
    } catch (_) { alert('ما قدرتش نقرا هذا الملف الصوتي / Could not read this audio file'); }
  });
  mic.addEventListener('click', async () => {
    if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(stream); chunks = [];
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop()); mic.classList.remove('recording');
        const raw = await new Blob(chunks).arrayBuffer();
        const decoded = await new AudioContext().decodeAudioData(raw);
        send({ text: input.value.trim(), audio: wav(decoded) });
      };
      recorder.start(); mic.classList.add('recording');
      setTimeout(() => recorder?.state === 'recording' && recorder.stop(), 20000);
    } catch (_) { alert('الميكروفون غير مسموح / Microphone not allowed'); }
  });
})();
