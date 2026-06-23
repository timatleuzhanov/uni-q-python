const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const W = 400, H = 650;
canvas.width = W; canvas.height = H;

const bgImage = new Image();
bgImage.src = './almau_flappybird.png';

const playerImage = new Image();
playerImage.src = './player.png';

const shieldImage = new Image();
shieldImage.src = './shield.png';

const coinImage = new Image();
coinImage.src = './coin.png';

const GRAVITY = 0.45;
const JUMP = -9.5;
const PIPE_SPEED = 3;
const PIPE_GAP = 155;
const PIPE_INTERVAL = 1800;

// --- State ---
let gameState = 'start';
let score = 0, bestScore = 0, frame = 0;
let lastPipe = 0, animFrame;
let doubleJumpUsed = false, lastTap = 0;
let isPaused = false, isMuted = false;

// Parallax
let buildingScroll = 0, groundScroll = 0;

// Shield
let shield = null;
let playerHasShield = false;
let shieldGlow = 0;
let pipesSpawned = 0;
let nextShieldPipe = 10 + Math.floor(Math.random() * 3);

// Death
let deathFlash = 0;
let deathTimer = 0;
let isDying = false;

// Coins
let totalCoins = parseInt(localStorage.getItem('almauCoins') || '0');
let sessionCoins = 0;
let coinOnScreen = null;
let nextCoinPipe = 4 + Math.floor(Math.random() * 3);
let invincible = 0;
let lifeUsedThisRound = false;

// Confetti
let confetti = [];
let newRecordConfetti = false;

// Start screen preview
let previewPlayer = { x: -50, y: H / 2 - 60, vx: 1.2 };
let previewPipes = [];
let previewLastPipe = 0;

// Audio
let audioCtx = null;

// Background music
const bgMusic = new Audio('./music.ogg');
bgMusic.loop = true;
bgMusic.volume = 0.25;
bgMusic.preload = 'auto';
bgMusic.setAttribute('playsinline', 'true');
let _bgMusicUnlocked = false;
// Функция `playBackgroundMusic` реализует локальную часть бизнес-логики модуля.
function playBackgroundMusic() {
  if (isMuted) return;
  bgMusic.play().catch(() => {});
}
// Функция `_unlockBgMusic` реализует локальную часть бизнес-логики модуля.
function _unlockBgMusic() {
  _bgMusicUnlocked = true;
  playBackgroundMusic();
}
document.addEventListener('click', _unlockBgMusic, { once: true });
document.addEventListener('touchstart', _unlockBgMusic, { once: true, passive: true });
document.addEventListener('keydown', _unlockBgMusic, { once: true });
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && _bgMusicUnlocked) playBackgroundMusic();
});

// --- Messages ---
const deathMessages = [
  "Эдвайзер ушёл на обед 😔",
  "Документы не приняты! Нужна печать. 🖨️",
  "Вы записаны на следующий семестр. 📅",
  "Пересдача! Академический должник. 😬",
  "Неприёмный день, приходите завтра. 🚪",
  "Очередь обнулилась. Попробуйте снова. 🔄",
  "Ваш номер истёк. Возьмите новый талон. 🎫",
  "Деканат закрыт на учёт. 📊",
  "GPA слишком низкий для прохода 📉",
  "Вы опоздали! Запись закрыта. ⏰",
  "Эдвайзер ушёл на корпоратив 🎉",
  "Твой номер очереди устарел 📋",
  "Деканат переехал, адрес неизвестен 🏃",
  "Препод поставил НЕ ЯВКА 😔",
  "Эдвайзер на больничном до конца семестра 🤒",
  "Твой дедлайн был вчера ⏰",
  "WiFi в AlmaU отключили, данные потеряны 📡",
  "Декан лично тебя отчислил 📜",
  "Пары начались, эдвайзинг закрыт 🚪",
  "Твой GPA не позволяет пройти дальше 📉",
  "Научрук отверг твою тему в последний момент 😱",
  "Бекарыс пропускает вас в не очереди",
  "Тима легенда",
  "Айбек прогульщик",
];

// --- Player ---
const player = {
  x: 80, y: H/2, vy: 0, w: 32, h: 32,
  angle: 0, alive: true, wingFrame: 0,
};

let pipes = [], particles = [], floatingTexts = [];
let bgStars = [];

for (let i = 0; i < 60; i++) {
  bgStars.push({
    x: Math.random() * W,
    y: Math.random() * H * 0.6,
    r: Math.random() * 1.5 + 0.3,
    speed: Math.random() * 0.3 + 0.1,
    alpha: Math.random() * 0.6 + 0.2
  });
}

// ===== AUDIO =====
function getAudio() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

// Функция `playSweep` реализует локальную часть бизнес-логики модуля.
function playSweep(f1, f2, dur, type, gain) {
  if (isMuted) return;
  try {
    const ac = getAudio();
    const osc = ac.createOscillator();
    const g = ac.createGain();
    osc.type = type || 'sine';
    osc.connect(g); g.connect(ac.destination);
    osc.frequency.setValueAtTime(f1, ac.currentTime);
    osc.frequency.linearRampToValueAtTime(f2, ac.currentTime + dur);
    g.gain.setValueAtTime(gain, ac.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + dur);
    osc.start(); osc.stop(ac.currentTime + dur + 0.05);
  } catch(e) {}
}

// Функция `playTone` реализует локальную часть бизнес-логики модуля.
function playTone(freq, dur, gain) {
  if (isMuted) return;
  try {
    const ac = getAudio();
    const osc = ac.createOscillator();
    const g = ac.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    osc.connect(g); g.connect(ac.destination);
    g.gain.setValueAtTime(gain, ac.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + dur);
    osc.start(); osc.stop(ac.currentTime + dur + 0.05);
  } catch(e) {}
}

// Функция `playSound` реализует локальную часть бизнес-логики модуля.
function playSound(type) {
  switch(type) {
    case 'jump':        playSweep(200, 400, 0.1, 'sine', 0.2); break;
    case 'score':       playTone(880, 0.15, 0.2); break;
    case 'shieldPick':
      [0, 80, 160].forEach((delay, i) => {
        setTimeout(() => playTone([523, 659, 784][i], 0.25, 0.15), delay);
      }); break;
    case 'shieldBreak': playSweep(300, 100, 0.3, 'sawtooth', 0.2); break;
    case 'death':       playSweep(400, 150, 0.5, 'sine', 0.25); break;
    case 'coin':        playTone(1047, 0.12, 0.18); break;
  }
}

const SVG_SOUND_ON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>';
const SVG_SOUND_OFF = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>';
const SVG_PAUSE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="white"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
const SVG_PLAY = '<svg width="18" height="18" viewBox="0 0 24 24" fill="white"><polygon points="5 3 19 12 5 21 5 3"/></svg>';

// Функция `toggleMute` реализует локальную часть бизнес-логики модуля.
function toggleMute() {
  isMuted = !isMuted;
  bgMusic.muted = isMuted;
  if (!isMuted) playBackgroundMusic();
  localStorage.setItem('almauMuted', isMuted);
  const icon = isMuted ? SVG_SOUND_OFF : SVG_SOUND_ON;
  document.getElementById('muteBtn').innerHTML = icon;
  document.getElementById('startMuteBtn').innerHTML = icon;
}

// ===== PAUSE =====
function togglePause() {
  if (gameState !== 'playing') return;
  isPaused = !isPaused;
  document.getElementById('pauseScreen').style.display = isPaused ? 'flex' : 'none';
  document.getElementById('pauseBtn').innerHTML = isPaused ? SVG_PLAY : SVG_PAUSE;
}

// ===== BACKGROUND =====
function drawBackground() {
  const moving = (gameState === 'playing' || gameState === 'dead') && !isPaused;

  const sky = ctx.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, '#07091f');
  sky.addColorStop(0.5, '#0d1535');
  sky.addColorStop(1, '#111d3a');
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, W, H);

  // Stars — parallax layer 1 (slowest)
  bgStars.forEach(s => {
    if (moving) s.x -= s.speed;
    if (s.x < 0) s.x = W;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.r, 0, Math.PI*2);
    ctx.fillStyle = `rgba(255,255,255,${s.alpha})`;
    ctx.fill();
  });

  // Building — parallax layer 2 (~4-5x slower than pipes)
  if (moving) buildingScroll += 0.7;
  drawBuildingImage();

  // Ground — parallax layer 3 (fast)
  if (moving) groundScroll += PIPE_SPEED + score * 0.04;

  ctx.fillStyle = '#0a0a0f';
  ctx.fillRect(0, H-60, W, 60);

  ctx.fillStyle = '#2a2a3f';
  ctx.fillRect(0, H-62, W, 2);

  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  const gx = -(groundScroll % 40);
  for (let i = 0; i < W + 40; i += 40) {
    ctx.beginPath();
    ctx.moveTo(gx + i, H-58);
    ctx.lineTo(gx + i, H);
    ctx.stroke();
  }

}

// Функция `drawBuildingImage` реализует локальную часть бизнес-логики модуля.
function drawBuildingImage() {
  if (!bgImage.complete || !bgImage.naturalWidth) return;

  const ox = -(buildingScroll % W);

  ctx.drawImage(bgImage, ox,     0, W, H);
  ctx.drawImage(bgImage, ox + W, 0, W, H);

  ctx.fillStyle = 'rgba(0, 0, 20, 0.4)';
  ctx.fillRect(0, 0, W, H);
}

// ===== PIPES =====
function drawPipe(pipe) {
  drawDocumentStack(pipe.x, 0, pipe.w, pipe.topH, true);
  const botY = pipe.topH + PIPE_GAP;
  drawDocumentStack(pipe.x, botY, pipe.w, H - botY - 60, false);

  const gapMid = pipe.topH + PIPE_GAP/2;
  const grd = ctx.createRadialGradient(pipe.x + pipe.w/2, gapMid, 0, pipe.x + pipe.w/2, gapMid, 80);
  grd.addColorStop(0, pipe.moving ? 'rgba(255,180,0,0.07)' : 'rgba(0,200,100,0.08)');
  grd.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grd;
  ctx.fillRect(pipe.x - 20, pipe.topH, pipe.w + 40, PIPE_GAP);


}

// Функция `drawDocumentStack` реализует локальную часть бизнес-логики модуля.
function drawDocumentStack(x, y, w, h, isTop) {
  if (h <= 0) return;
  const layers = Math.max(1, Math.floor(h / 18));
  const layerH = h / layers;

  for (let i = 0; i < layers; i++) {
    const ly = y + i * layerH;
    const offset = (i % 2 === 0) ? 0 : 2;
    const shade = 220 + (i % 3) * 12;
    ctx.fillStyle = `rgb(${shade},${shade-10},${shade-20})`;
    ctx.fillRect(x + offset, ly + 1, w - offset*2, layerH - 2);

    ctx.fillStyle = 'rgba(100,100,150,0.3)';
    for (let l = 0; l < 3; l++) {
      ctx.fillRect(x + offset + 6, ly + 5 + l*4, w - offset*2 - 12, 1);
    }

    if (i % 5 === 0) {
      ctx.fillStyle = 'rgba(0,80,200,0.4)';
      ctx.font = 'bold 6px Nunito';
      ctx.textAlign = 'center';
      ctx.fillText('AlmaU', x + w/2, ly + 10);
    }
  }

  const eg1 = ctx.createLinearGradient(x, 0, x+8, 0);
  eg1.addColorStop(0, 'rgba(0,0,0,0.4)'); eg1.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = eg1; ctx.fillRect(x, y, 10, h);

  const eg2 = ctx.createLinearGradient(x+w-8, 0, x+w, 0);
  eg2.addColorStop(0, 'rgba(0,0,0,0)'); eg2.addColorStop(1, 'rgba(0,0,0,0.4)');
  ctx.fillStyle = eg2; ctx.fillRect(x+w-10, y, 10, h);
}

// ===== SHIELD =====
function drawShield() {
  if (!shield) return;

  if (gameState === 'playing' && !isPaused) {
    shield.x -= PIPE_SPEED + score * 0.04;
    shield.phase += 0.08;
  }

  if (shield.x < -30) { shield = null; return; }

  const pulse = 0.25 + Math.sin(shield.phase) * 0.12;
  const glow = ctx.createRadialGradient(shield.x, shield.y, 0, shield.x, shield.y, 34);
  glow.addColorStop(0, `rgba(0,160,255,${pulse})`);
  glow.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(shield.x, shield.y, 34, 0, Math.PI*2);
  ctx.fill();

  const shieldSize = 38;
  ctx.drawImage(shieldImage, shield.x - shieldSize / 2, shield.y - shieldSize / 2, shieldSize, shieldSize);

  if (gameState === 'playing' && !isPaused) {
    const dx = shield.x - (player.x + player.w/2);
    const dy = shield.y - (player.y + player.h/2);
    if (Math.sqrt(dx*dx + dy*dy) < 22) {
      playerHasShield = true;
      shield = null;
      playSound('shieldPick');
      floatingTexts.push({
        x: player.x + 20, y: player.y - 15,
        text: '🛡️ ЩИТ!', color: '#00ccff', size: 14,
        life: 55, maxLife: 55
      });
    }
  }
}

// ===== COIN =====
function drawCoin() {
  if (!coinOnScreen) return;

  if (gameState === 'playing' && !isPaused) {
    coinOnScreen.x -= PIPE_SPEED + score * 0.04;
    coinOnScreen.phase += 0.06;
  }

  if (coinOnScreen.x < -20) { coinOnScreen = null; return; }

  const x = coinOnScreen.x;
  const y = coinOnScreen.baseY + Math.sin(coinOnScreen.phase) * 6;
  const r = 15;
  const drawR = 20;

  // Outer glow
  const glow = ctx.createRadialGradient(x, y, 0, x, y, r * 2.2);
  glow.addColorStop(0, 'rgba(255,200,0,0.25)');
  glow.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = glow;
  ctx.beginPath(); ctx.arc(x, y, r * 2.2, 0, Math.PI*2); ctx.fill();

  ctx.drawImage(coinImage, x - drawR - 7.5, y - drawR - 7.5, drawR * 2 + 15, drawR * 2 + 15);

  // Collision
  if (gameState === 'playing' && !isPaused) {
    const dx = x - (player.x + player.w/2);
    const dy = y - (player.y + player.h/2);
    if (Math.sqrt(dx*dx + dy*dy) < r + player.w/2) {
      coinOnScreen = null;
      totalCoins++;
      sessionCoins++;
      localStorage.setItem('almauCoins', totalCoins);
      playSound('coin');
      floatingTexts.push({
        x: player.x + 20, y: player.y - 15,
        text: '+1 GPA', coinIcon: true, color: '#ffcc00', size: 13,
        life: 45, maxLife: 45
      });
    }
  }
}

// ===== PLAYER =====
function drawPlayer() {
  ctx.save();
  const cx = player.x + player.w/2;
  const cy = player.y + player.h/2;
  ctx.translate(cx, cy);

  const targetAngle = Math.max(-0.5, Math.min(0.8, player.vy * 0.06));
  player.angle += (targetAngle - player.angle) * 0.15;
  ctx.rotate(player.angle);

  // Shield / break aura
  if (playerHasShield || shieldGlow > 0) {
    if (shieldGlow > 0) shieldGlow--;
    const t = playerHasShield ? (0.5 + Math.sin(frame * 0.15) * 0.2) : (shieldGlow / 40) * 0.7;
    const auraColor = shieldGlow > 0 ? `rgba(255,120,0,${t})` : `rgba(0,160,255,${t})`;
    const auraGrd = ctx.createRadialGradient(0, 0, 8, 0, 0, 37);
    auraGrd.addColorStop(0, shieldGlow > 0 ? `rgba(255,120,0,${t*0.5})` : `rgba(0,160,255,${t*0.5})`);
    auraGrd.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = auraGrd;
    ctx.beginPath(); ctx.arc(0, 0, 37, 0, Math.PI*2); ctx.fill();
    ctx.beginPath(); ctx.arc(0, 0, 33, 0, Math.PI*2);
    ctx.strokeStyle = auraColor; ctx.lineWidth = 2.5; ctx.stroke();
  }

  const drawW = 85, drawH = 85;
  ctx.drawImage(playerImage, -drawW/2, -drawH/2, drawW, drawH);

  ctx.restore();
}

// ===== PARTICLES =====
function drawParticles() {
  const ground = H - 62;
  particles = particles.filter(p => p.life > 0);
  particles.forEach(p => {
    if (!p.landed) {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.32;
      p.rotation += p.rotSpeed;
      if (p.y + p.h * 0.5 >= ground) {
        p.y = ground - p.h * 0.5;
        p.vy = 0;
        p.vx *= 0.25;
        p.rotSpeed = 0;
        p.landed = true;
      }
    } else {
      p.vx *= 0.8;
      p.x += p.vx;
    }
    p.life--;

    ctx.save();
    ctx.globalAlpha = p.life < 25 ? p.life / 25 : 1;
    ctx.translate(p.x, p.y);
    ctx.rotate(p.rotation);

    ctx.fillStyle = '#f2ede3';
    ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);

    ctx.fillStyle = 'rgba(0, 60, 160, 0.4)';
    ctx.fillRect(-p.w / 2, -p.h / 2, p.w * 0.32, p.h * 0.24);

    ctx.strokeStyle = 'rgba(0, 0, 80, 0.3)';
    ctx.lineWidth = 0.7;
    [0.44, 0.66, 0.86].forEach(t => {
      const ly = -p.h / 2 + p.h * t;
      ctx.beginPath();
      ctx.moveTo(-p.w / 2 + 2, ly);
      ctx.lineTo(p.w / 2 - 2, ly);
      ctx.stroke();
    });

    ctx.restore();
  });
  ctx.globalAlpha = 1;
}

// Функция `drawFloatingTexts` реализует локальную часть бизнес-логики модуля.
function drawFloatingTexts() {
  floatingTexts = floatingTexts.filter(t => t.life > 0);
  floatingTexts.forEach(t => {
    t.y -= 0.5; t.life--;
    ctx.globalAlpha = t.life / t.maxLife;
    ctx.fillStyle = t.color || '#ffdd00';
    ctx.font = `bold ${t.size || 14}px Nunito`;
    ctx.textAlign = 'center';
    ctx.fillText(t.text, t.x, t.y);
    if (t.coinIcon) {
      const textW = ctx.measureText(t.text).width;
      ctx.drawImage(coinImage, t.x + textW / 2 + 4, t.y - 12, 35, 35);
    }
    ctx.globalAlpha = 1;
  });
}

// Функция `addParticles` реализует локальную часть бизнес-логики модуля.
function addParticles(x, y) {
  for (let i = 0; i < 22; i++) {
    const angle = -(0.08 + Math.random() * 0.84) * Math.PI;
    const speed = 3 + Math.random() * 9;
    particles.push({
      x: x + (Math.random() - 0.5) * 14,
      y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      w: 13 + Math.random() * 10,
      h: 10 + Math.random() * 7,
      rotation: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.22,
      life: 130, maxLife: 130,
      landed: false
    });
  }
}

// ===== CONFETTI =====
const CONFETTI_COLORS = ['#FFD700','#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD'];

// Функция `spawnConfetti` реализует локальную часть бизнес-логики модуля.
function spawnConfetti() {
  const count = 80 + Math.floor(Math.random() * 21);
  for (let i = 0; i < count; i++) {
    const maxLife = 120 + Math.floor(Math.random() * 31);
    confetti.push({
      x: Math.random() * W,
      y: -10,
      vx: (Math.random() - 0.5) * 6,
      vy: 2 + Math.random() * 4,
      color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
      rotation: Math.random() * Math.PI * 2,
      rotationSpeed: (Math.random() - 0.5) * 0.2,
      life: maxLife, maxLife
    });
  }
}

// Функция `drawConfetti` реализует локальную часть бизнес-логики модуля.
function drawConfetti() {
  confetti = confetti.filter(c => c.life > 0 && c.y < H + 20);
  confetti.forEach(c => {
    c.x += c.vx;
    c.y += c.vy;
    c.vy += 0.1;
    c.rotation += c.rotationSpeed;
    c.life--;
    ctx.save();
    ctx.globalAlpha = c.life <= 30 ? c.life / 30 : 1;
    ctx.translate(c.x, c.y);
    ctx.rotate(c.rotation);
    ctx.fillStyle = c.color;
    ctx.fillRect(-3, -5, 6, 10);
    ctx.restore();
  });
  ctx.globalAlpha = 1;
}

// ===== HUD =====
function addScorePopup(x, y) {
  const msgs = ['+1 место!','Молодец!','Дальше!','Вперёд!','Да!'];
  floatingTexts.push({
    x, y,
    text: msgs[Math.floor(Math.random()*msgs.length)],
    color: score % 5 === 0 ? '#ffdd00' : '#aaffaa',
    size: score % 5 === 0 ? 16 : 13,
    life: 50, maxLife: 50
  });
}

// Функция `drawHUD` реализует локальную часть бизнес-логики модуля.
function drawHUD() {
  if (gameState !== 'playing') return;

  document.getElementById('score').style.display = 'block';
  document.getElementById('score').textContent = score;
  document.getElementById('queueStatus').style.display = 'block';
  document.getElementById('queueStatus').textContent = `📋 Ты продвинулся на ${score} мест в очереди`;
  document.getElementById('coinDisplay').style.display = 'block';
  document.getElementById('coinCount').textContent = totalCoins;

  if (playerHasShield) {
    ctx.fillStyle = 'rgba(0,200,255,0.7)';
    ctx.font = 'bold 10px Nunito';
    ctx.textAlign = 'left';
    ctx.fillText('🛡️ Щит активен', 12, H-75);
  }
}

// Функция `drawReadyHint` реализует локальную часть бизнес-логики модуля.
function drawReadyHint() {
  const alpha = 0.4 + Math.sin(frame * 0.08) * 0.4;
  ctx.globalAlpha = alpha;
  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 11px "Press Start 2P", monospace';
  ctx.textAlign = 'center';
  ctx.fillText('ТАП ДЛЯ СТАРТА', W/2, H/2 + 80);
  ctx.globalAlpha = 1;
}

// ===== GAME LOGIC =====
function spawnPipe() {
  const minTop = 80, maxTop = H - PIPE_GAP - 120;
  const topH = Math.floor(Math.random() * (maxTop - minTop) + minTop);
  const isMoving = (pipesSpawned % 9 === 8);
  pipes.push({
    x: W + 10, topH, baseTopH: topH, w: 52, passed: false,
    moving: isMoving, movePhase: Math.random() * Math.PI * 2
  });

  pipesSpawned++;

  if (pipesSpawned >= nextCoinPipe && !coinOnScreen) {
    coinOnScreen = {
      x: W + 36,
      baseY: topH + PIPE_GAP/2 + (Math.random() - 0.5) * 60,
      phase: Math.random() * Math.PI * 2
    };
    nextCoinPipe = pipesSpawned + 4 + Math.floor(Math.random() * 3);
  }

  if (pipesSpawned >= nextShieldPipe && !shield && !playerHasShield) {
    shield = {
      x: W + 36,
      y: topH + PIPE_GAP/2 + (Math.random() - 0.5) * (PIPE_GAP * 0.4),
      phase: 0
    };
    nextShieldPipe = pipesSpawned + 10 + Math.floor(Math.random() * 3);
  }
}

// Функция `updatePipes` реализует локальную часть бизнес-логики модуля.
function updatePipes() {
  const now = Date.now();
  if (now - lastPipe > PIPE_INTERVAL) {
    spawnPipe();
    lastPipe = now;
  }

  const speed = PIPE_SPEED + score * 0.04;
  pipes.forEach(p => {
    p.x -= speed;
    if (p.moving) {
      p.movePhase += 0.02;
      p.topH = p.baseTopH + Math.sin(p.movePhase) * 35;
    }
  });
  pipes = pipes.filter(p => p.x > -p.w - 10);

  pipes.forEach(p => {
    if (!p.passed && p.x + p.w < player.x) {
      p.passed = true;
      score++;
      if (score > bestScore) {
        bestScore = score;
        if (!newRecordConfetti) {
          newRecordConfetti = true;
          spawnConfetti();
          floatingTexts.push({
            x: W/2, y: H/2 - 60,
            text: '🏆 НОВЫЙ РЕКОРД!', color: '#FFD700', size: 20,
            life: 120, maxLife: 120
          });
        }
      }
      playSound('score');
      addScorePopup(player.x + 30, player.y);

      if (score % 10 === 0) {
        floatingTexts.push({
          x: W/2, y: H/2 - 40,
          text: score === 10 ? '🎉 10 мест — отлично!' :
                score === 20 ? '🔥 Ты стремительно идёшь!' :
                score === 30 ? '⭐ Почти у эдвайзера!' : `🏆 ${score} мест пройдено!`,
          color: '#ffdd00', size: 16, life: 80, maxLife: 80
        });
      }
    }

    const px = player.x + 4, py = player.y + 4;
    const pw = player.w - 8, ph = player.h - 8;
    if (px < p.x + p.w && px + pw > p.x) {
      if (py < p.topH || py + ph > p.topH + PIPE_GAP) {
        if (playerHasShield) {
          playerHasShield = false;
          shieldGlow = 40;
          p.x = -999; // удаляем столб с которым столкнулись
          playSound('shieldBreak');
          particles.push({
            x: player.x + player.w/2, y: player.y + player.h/2,
            vx: 0, vy: 0, text: '💥', size: 36, color: '#fff',
            life: 20, maxLife: 20
          });
          floatingTexts.push({
            x: player.x + 20, y: player.y - 15,
            text: '💥 ЩИТ СЛОМАН!', color: '#ffaa00', size: 12,
            life: 55, maxLife: 55
          });
        } else {
          die();
        }
      }
    }
  });

  if (player.y + player.h >= H - 60 || player.y <= 0) die();
}

// Функция `die` реализует локальную часть бизнес-логики модуля.
function die() {
  addParticles(player.x + player.w/2, player.y + player.h/2);
  if (!player.alive) return;
  if (invincible > 0) return;

  player.alive = false;
  gameState = 'dead';
  if (navigator.vibrate) navigator.vibrate(200);
  playSound('death');
  deathTimer = 0;
  isDying = true;
}

// Функция `showGameOver` реализует локальную часть бизнес-логики модуля.
function showGameOver() {
  document.getElementById('score').style.display = 'none';
  document.getElementById('queueStatus').style.display = 'none';
  document.getElementById('topControls').style.display = 'none';
  document.getElementById('coinDisplay').style.display = 'none';

  const msg = deathMessages[Math.floor(Math.random() * deathMessages.length)];
  const medal = score >= 30 ? '🏆' : score >= 20 ? '🥇' : score >= 10 ? '🥈' : score >= 5 ? '🥉' : '😔';

  document.getElementById('medal').textContent = medal;
  document.getElementById('goMessage').textContent = msg;
  document.getElementById('finalScore').textContent = score;
  document.getElementById('bestScoreDisplay').textContent = bestScore;

  const title = score >= 30 ? 'КРАСНЫЙ ДИПЛОМ! 🎓' :
                score >= 20 ? 'ХОРОШИСТ! 👍' :
                score >= 10 ? 'ТРОЕЧНИК 😅' : 'ПЕРЕСДАЧА!';
  document.getElementById('goTitle').textContent = title;
  document.getElementById('goTitle').style.color =
    score >= 30 ? '#ffdd00' : score >= 20 ? '#00ff88' : '#ff4444';

  document.getElementById('goCoins').textContent = `+${sessionCoins} GPA за раунд`;
  document.getElementById('goTotalCoins').textContent = `Всего GPA: ${totalCoins}`;

  const btn = document.getElementById('continueBtn');
  if (lifeUsedThisRound) {
    btn.style.display = 'none';
  } else {
    btn.style.display = '';
    if (totalCoins >= 5) {
      btn.disabled = false;
      btn.textContent = '🪙 Продолжить за 5 GPA';
      btn.classList.remove('btn-coin--disabled');
    } else {
      btn.disabled = true;
      btn.textContent = `Недостаточно GPA (нужно 5)`;
      btn.classList.add('btn-coin--disabled');
    }
  }

  document.getElementById('gameOverScreen').style.display = 'flex';
}

// Функция `startGame` реализует локальную часть бизнес-логики модуля.
function startGame() {
  document.getElementById('startScreen').style.display = 'none';
  document.getElementById('gameOverScreen').style.display = 'none';
  document.getElementById('score').style.display = 'none';
  document.getElementById('queueStatus').style.display = 'none';
  document.getElementById('pauseScreen').style.display = 'none';
  document.getElementById('topControls').style.display = 'none';

  pipes = []; particles = []; floatingTexts = [];
  shield = null; playerHasShield = false; shieldGlow = 0; deathFlash = 0; deathTimer = 0; isDying = false;
  coinOnScreen = null; sessionCoins = 0; invincible = 0;
  score = 0; frame = 0;
  doubleJumpUsed = false; isPaused = false;
  pipesSpawned = 0;
  nextShieldPipe = 10 + Math.floor(Math.random() * 3);
  nextCoinPipe = 4 + Math.floor(Math.random() * 3);
  lifeUsedThisRound = false;
  newRecordConfetti = false;
  confetti = [];
  document.getElementById('coinDisplay').style.display = 'none';

  player.y = H/2 - 20;
  player.vy = 0; player.angle = 0; player.alive = true;

  gameState = 'ready';
  if (_bgMusicUnlocked) playBackgroundMusic();
}

// Функция `goToMainMenu` реализует локальную часть бизнес-логики модуля.
function goToMainMenu() {
  document.getElementById('gameOverScreen').style.display = 'none';
  document.getElementById('pauseScreen').style.display = 'none';
  document.getElementById('startScreen').style.display = 'flex';
  document.getElementById('score').style.display = 'none';
  document.getElementById('queueStatus').style.display = 'none';
  document.getElementById('topControls').style.display = 'none';

  pipes = []; particles = []; floatingTexts = [];
  shield = null; playerHasShield = false; shieldGlow = 0; deathFlash = 0; deathTimer = 0; isDying = false;
  coinOnScreen = null; sessionCoins = 0; invincible = 0;
  score = 0; frame = 0; isPaused = false;
  player.y = H/2; player.vy = 0; player.angle = 0; player.alive = true;
  document.getElementById('coinDisplay').style.display = 'none';
  document.getElementById('startCoinCount').textContent = totalCoins;
  previewPipes = [];
  previewLastPipe = 0;
  previewPlayer = { x: -50, y: H / 2 - 60, vx: 1.2 };
  gameState = 'start';
}

// Функция `continueByCoin` реализует локальную часть бизнес-логики модуля.
function continueByCoin() {
  if (totalCoins < 5) return;
  totalCoins -= 5;
  lifeUsedThisRound = true;
  localStorage.setItem('almauCoins', totalCoins);

  document.getElementById('gameOverScreen').style.display = 'none';
  document.getElementById('score').style.display = 'block';
  document.getElementById('queueStatus').style.display = 'block';
  document.getElementById('topControls').style.display = 'flex';
  document.getElementById('coinDisplay').style.display = 'block';

  pipes = [];
  coinOnScreen = null;
  lastPipe = Date.now() + 2500;
  deathFlash = 0; deathTimer = 0; isDying = false;

  player.y = H/2;
  player.vy = 0;
  player.angle = 0;
  player.alive = true;
  invincible = 120;

  gameState = 'playing';

  floatingTexts.push({
    x: W/2, y: H/2 - 60,
    text: 'Продолжаем! 💪', color: '#00ff88', size: 16,
    life: 90, maxLife: 90
  });
}

// ===== JUMP =====
function jump() {
  if (gameState === 'dead' || gameState === 'start' || isPaused) return;
  if (!player.alive) return;

  if (gameState === 'ready') {
    gameState = 'playing';
    lastPipe = Date.now() + 1000;
    player.vy = JUMP;
    doubleJumpUsed = false;
    document.getElementById('topControls').style.display = 'flex';
    playSound('jump');
    return;
  }

  playSound('jump');
  if (player.vy < 3 || !doubleJumpUsed === false) {
    player.vy = JUMP;
    doubleJumpUsed = false;
  } else if (!doubleJumpUsed) {
    player.vy = JUMP * 0.85;
    doubleJumpUsed = true;
  }
}

// ===== START SCREEN PREVIEW =====
function updateDrawStartScreen() {
  const PREVIEW_SPEED = PIPE_SPEED / 3;

  const now = Date.now();
  if (now - previewLastPipe > 2200) {
    const minTop = 80, maxTop = H - PIPE_GAP - 120;
    previewPipes.push({
      x: W + 10,
      topH: Math.floor(Math.random() * (maxTop - minTop) + minTop),
      w: 52, moving: false
    });
    previewLastPipe = now;
  }
  previewPipes.forEach(p => { p.x -= PREVIEW_SPEED; });
  previewPipes = previewPipes.filter(p => p.x > -70);
  previewPipes.forEach(p => drawPipe(p));

  previewPlayer.x += previewPlayer.vx;
  previewPlayer.y = H / 2 - 60 + Math.sin(frame * 0.04) * 22;
  if (previewPlayer.x > W + 60) previewPlayer.vx = -1.2;
  if (previewPlayer.x < -60) previewPlayer.vx = 1.2;

  const drawW = 85, drawH = 85;
  ctx.save();
  ctx.translate(previewPlayer.x, previewPlayer.y);
  if (previewPlayer.vx < 0) ctx.scale(-1, 1);
  ctx.drawImage(playerImage, -drawW / 2, -drawH / 2, drawW, drawH);
  ctx.restore();
}

// ===== GAME LOOP =====
function gameLoop() {
  try {
  ctx.clearRect(0, 0, W, H);
  if (!isPaused) frame++;

  drawBackground();

  if (gameState === 'playing' || gameState === 'dead') {
    pipes.forEach(p => drawPipe(p));
    drawShield();
    drawCoin();

    if (gameState === 'playing' && !isPaused) {
      player.vy += GRAVITY;
      player.y += player.vy;
      if (player.vy > 0) doubleJumpUsed = false;
      updatePipes();
    }

    if (player.alive) {
      if (invincible > 0) {
        invincible--;
        if (Math.floor(invincible / 5) % 2 === 0) drawPlayer();
      } else {
        drawPlayer();
      }
    }
    if (isDying && deathTimer <= 12) {
      ctx.fillStyle = `rgba(255,80,80,${((12 - deathTimer) / 12) * 0.45})`;
      ctx.fillRect(0, 0, W, H);
    }
    drawParticles();
    drawFloatingTexts();
    drawConfetti();
    drawHUD();
  }

  if (gameState === 'ready') {
    player.y = H/2 - 20 + Math.sin(frame * 0.05) * 8;
    player.vy = 0;
    drawPlayer();
    drawReadyHint();
  }

  if (gameState === 'start') {
    updateDrawStartScreen();
  }

  if (isDying) {
    deathTimer++;
    if (deathTimer >= 55) {
      isDying = false;
      showGameOver();
    }
  }
  } catch(e) {}
  animFrame = requestAnimationFrame(gameLoop);
}

// ===== EVENTS =====
let _isTouchDevice = false;

document.addEventListener('keydown', e => {
  if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'KeyW') {
    e.preventDefault();
    jump();
  }
  if (e.code === 'Escape' || e.code === 'KeyP') {
    togglePause();
  }
});

canvas.addEventListener('click', () => {
  if (_isTouchDevice) return;
  if (gameState !== 'playing' && gameState !== 'ready') return;
  if (!isPaused) jump();
});

document.addEventListener('touchstart', e => {
  e.preventDefault();
  _isTouchDevice = true;
  _unlockBgMusic();
  if (e.target.closest('button, .btn, .ctrl-btn, #homeBtn, .btn-outline')) return;
  if (gameState !== 'playing' && gameState !== 'ready') return;
  if (!isPaused) jump();
}, { passive: false });

document.querySelectorAll('.btn, .ctrl-btn, #homeBtn, .btn-outline').forEach(btn => {
  btn.addEventListener('touchstart', e => e.stopPropagation(), { passive: false });
});

document.getElementById('startMuteBtn').addEventListener('touchstart', e => {
  e.preventDefault();
  e.stopPropagation();
  toggleMute();
}, { passive: false });

document.getElementById('startCoinCount').textContent = totalCoins;

// Apply saved mute state
(function() {
  const saved = localStorage.getItem('almauMuted') === 'true';
  if (saved) {
    isMuted = true;
    bgMusic.muted = true;
    document.getElementById('muteBtn').innerHTML = SVG_SOUND_OFF;
    document.getElementById('startMuteBtn').innerHTML = SVG_SOUND_OFF;
  }
})();

bgImage.onload = () => gameLoop();
bgImage.onerror = () => gameLoop(); // fallback если файл недоступен
