/* Sarsma tablası — Arduino Nano step üreteci
 * IAC 2026 · A2 · Real-Time Active Vibration Compensation
 *
 * Donanım:  Arduino Nano (ATmega328P, 16 MHz) → DM542 → NEMA 23 57HB84-154
 *           GT2 20 diş kasnak, 1/16 mikro adım → 3200 adım/tur, 40 mm/tur
 *           = 12.5 µm/adım
 *
 * Bağlantı: D9  → PUL-      D8  → DIR-      PUL+/DIR+ → 5V
 *           DM542 girişleri optik yalıtımlı; 48 V tarafıyla ortak toprak YOK.
 *
 *
 * MİMARİ
 * ------
 * İki zamanlayıcı, iki iş:
 *
 *   Timer2  →  1 kHz "tick". Her tick'te bir hedef konum üretilir (mod'a göre)
 *              ve o tick içinde atılacak adım sayısı hesaplanır.
 *   Timer1  →  adım darbeleri. Tick başında, o tick'in adımlarını 1 ms'e eşit
 *              aralıkla yayacak şekilde kurulur.
 *
 * Konum HER ZAMAN atılan darbelerin sayımıdır (`position`). Hiçbir mod konumu
 * tahmin etmez; hepsi bir hedef konum söyler ve fark kadar adım atılır.
 *
 *
 * NEDEN AKIŞTA MUTLAK KONUM, FARK DEĞİL
 * -------------------------------------
 * Bilgisayardan gelen dalga formu int16 *mutlak* konumlardan oluşur, adım
 * farklarından değil. Fark gönderilseydi tek bir kayıp örnek kalıcı bir kaymaya
 * dönüşürdü ve bunu hiçbir yerden anlayamazdık — tabla deneyin geri kalanında
 * sessizce yanlış yerde dururdu. Mutlak konumda kayıp örnek bir sonraki örnekte
 * kendini düzeltir. ±32767 adım = ±409 mm; bizim strok ±150 mm.
 *
 *
 * NEDEN UNDERRUN SAYILIYOR
 * ------------------------
 * USB seri hattı gerçek zamanlı değil. Dizüstü bir an takılırsa tampon boşalır
 * ve tabla dalga formunun ortasında durur. Bu HATA SESSİZDİR: kayıt normal
 * görünür, sadece titreşim bir süre yoktur. Bu yüzden her boşalma sayılır ve
 * durum satırında raporlanır. `under > 0` ise o koşu geçersizdir — masaüstü
 * uygulaması koşuyu kırmızı işaretler.
 *
 *
 * PROTOKOL  (115200 değil — 250000 baud, 16 MHz'de hatasız bölünüyor)
 * ---------
 * Ayrıştırıcı her an iki durumdan birinde: ya satır okuyor, ya tam olarak 2N
 * ikili bayt. Karışma ihtimali yok.
 *
 *   ?                 durum satırı iste
 *   H                 şu anki konumu sıfır kabul et
 *   L <min> <max>     yazılım sınırı (adım)
 *   J <hız>           serbest sürüş, adım/s işaretli; 0 = dur
 *   G <konum> <hız>   mutlak konuma git
 *   N <frekans_mHz> <genlik_adım>    sinüs (frekans milihertz)
 *   R <n>             akışa hazırlan, n örnek gelecek (0 = süresiz)
 *   D <n>             ARDINDAN tam 2n bayt int16 little-endian mutlak konum
 *   X                 dur (her modda, her an)
 *   !                 acil dur — akış tamponunu da boşaltır
 *
 * Cevaplar:
 *   S <pos> <mode> <free> <under> <clip> <target>   durum, 20 Hz
 *   K <mesaj>   komut kabul        E <mesaj>   hata
 */

#include <util/atomic.h>
#include <avr/pgmspace.h>

/* ---- donanım sabitleri ---- */
#define PIN_STEP_MASK  _BV(PB1)      /* D9  */
#define PIN_DIR_MASK   _BV(PB0)      /* D8  */
#define PULSE_US       4             /* DM542 en az ~2.5 µs ister */

#define TICK_HZ        1000
#define BAUD_RATE      250000

/* Bir tick'te atılabilecek en fazla adım. 20 adım/ms = 20000 adım/s = 250 mm/s.
   Bizim en yüksek hız 25×'te ~125 mm/s, yani iki kat pay var. Bunu aşan bir
   hedef sessizce kırpılmaz — `clip` sayacı artar ve koşu şaibeli sayılır. */
#define MAX_STEPS_PER_TICK  20

/* Akış tamponu: 256 örnek = 256 ms. Nano'nun 2 KB RAM'inin 512 baytı. */
#define BUF_N          256
#define BUF_MASK       (BUF_N - 1)

enum Mode : uint8_t { M_IDLE = 0, M_JOG, M_GOTO, M_SINE, M_STREAM };

/* ---- ISR ile paylaşılan durum ---- */
volatile int32_t  position     = 0;      /* atılan adımların sayımı */
volatile int32_t  targetPos    = 0;
volatile uint16_t stepsLeft    = 0;
volatile int8_t   dirSign      = 1;
volatile uint8_t  mode         = M_IDLE;
volatile uint16_t underruns    = 0;      /* tampon boşaldı */
volatile uint16_t clips        = 0;      /* hız veya sınır kırpması */

volatile int32_t  limMin       = -100000L;
volatile int32_t  limMax       =  100000L;

/* JOG / GOTO: hız, 8 kesirli bitle adım/tick */
volatile int32_t  velQ8        = 0;
volatile int32_t  posQ8        = 0;      /* JOG'un biriktirdiği kesirli konum */
volatile int32_t  gotoTarget   = 0;

/* SINE: 32 bit faz biriktirici, üst 8 bit tabloya indeks.
   16 bit yetmiyor: 1 Hz'de artış 65.5 çıkıyor ve 65'e yuvarlanınca frekans %0.8
   kayıyor. Geçirgenlik taramasında rezonans tepesini bu hatayla arayamayız. */
volatile uint32_t sinPhase     = 0;
volatile uint32_t sinInc       = 0;
volatile int32_t  sinAmp       = 0;      /* o anki genlik */
volatile int32_t  sinAmpTgt    = 0;      /* gidilen genlik */
volatile int32_t  sinAmpStep   = 1;      /* tick başına yaklaşma */
volatile int32_t  sinCentre    = 0;

/* Genlik hiçbir zaman bir anda değişmiyor, ~0.4 s'de yumuşayarak gidiyor.
   Sebebi: konum = merkez + genlik·sin(faz). Genliği anında değiştirirseniz
   konum sin(faz) kadar sıçrar — sinüsün tepesindeyken genliği 1 mm artırmak
   tablayı tek tick'te 1 mm ötelemek demek, ki bu 80 adım/ms, tavanın dört katı.
   Yumuşak geçiş ayrıca başlatma ve durdurmayı da şoksuz yapıyor. */
#define AMP_RAMP_TICKS 400

/* akış halka tamponu */
volatile int16_t  ring[BUF_N];
volatile uint8_t  rHead = 0, rTail = 0;   /* head = yazılan, tail = okunan */
volatile uint32_t streamLeft = 0;         /* kalan örnek; 0xFFFFFFFF = süresiz */
volatile bool     streamEnded = false;

/* Akış, tampon dolmadan BAŞLAMAZ. Aksi halde 'R' ile M_STREAM'e geçer geçmez
   ilk tick boş tampon görür ve daha bilgisayar tek bayt göndermeden underrun
   sayacı artar — koşu daha başlamadan geçersiz damgası yer. */
#define PRIME_N        64                 /* 64 ms ön tampon */
volatile bool     streamArmed = false;
volatile uint8_t  primeN      = PRIME_N;  /* kısa dalga formunda daha az */

static const int16_t SIN256[256] PROGMEM = {
       0,    804,   1608,   2410,   3212,   4011,   4808,   5602,
    6393,   7179,   7962,   8739,   9512,  10278,  11039,  11793,
   12539,  13279,  14010,  14732,  15446,  16151,  16846,  17530,
   18204,  18868,  19519,  20159,  20787,  21403,  22005,  22594,
   23170,  23731,  24279,  24811,  25329,  25832,  26319,  26790,
   27245,  27683,  28105,  28510,  28898,  29268,  29621,  29956,
   30273,  30571,  30852,  31113,  31356,  31580,  31785,  31971,
   32137,  32285,  32412,  32521,  32609,  32678,  32728,  32757,
   32767,  32757,  32728,  32678,  32609,  32521,  32412,  32285,
   32137,  31971,  31785,  31580,  31356,  31113,  30852,  30571,
   30273,  29956,  29621,  29268,  28898,  28510,  28105,  27683,
   27245,  26790,  26319,  25832,  25329,  24811,  24279,  23731,
   23170,  22594,  22005,  21403,  20787,  20159,  19519,  18868,
   18204,  17530,  16846,  16151,  15446,  14732,  14010,  13279,
   12539,  11793,  11039,  10278,   9512,   8739,   7962,   7179,
    6393,   5602,   4808,   4011,   3212,   2410,   1608,    804,
       0,   -804,  -1608,  -2410,  -3212,  -4011,  -4808,  -5602,
   -6393,  -7179,  -7962,  -8739,  -9512, -10278, -11039, -11793,
  -12539, -13279, -14010, -14732, -15446, -16151, -16846, -17530,
  -18204, -18868, -19519, -20159, -20787, -21403, -22005, -22594,
  -23170, -23731, -24279, -24811, -25329, -25832, -26319, -26790,
  -27245, -27683, -28105, -28510, -28898, -29268, -29621, -29956,
  -30273, -30571, -30852, -31113, -31356, -31580, -31785, -31971,
  -32137, -32285, -32412, -32521, -32609, -32678, -32728, -32757,
  -32767, -32757, -32728, -32678, -32609, -32521, -32412, -32285,
  -32137, -31971, -31785, -31580, -31356, -31113, -30852, -30571,
  -30273, -29956, -29621, -29268, -28898, -28510, -28105, -27683,
  -27245, -26790, -26319, -25832, -25329, -24811, -24279, -23731,
  -23170, -22594, -22005, -21403, -20787, -20159, -19519, -18868,
  -18204, -17530, -16846, -16151, -15446, -14732, -14010, -13279,
  -12539, -11793, -11039, -10278,  -9512,  -8739,  -7962,  -7179,
   -6393,  -5602,  -4808,  -4011,  -3212,  -2410,  -1608,   -804,
};

/* ======================= adım darbeleri (Timer1) ======================= */

ISR(TIMER1_COMPA_vect) {
  if (stepsLeft == 0) { TIMSK1 &= ~_BV(OCIE1A); return; }
  PORTB |= PIN_STEP_MASK;
  stepsLeft--;
  position += dirSign;
  /* DM542'nin darbe genişliği için ~4 µs. Adım hızı en fazla 20 kHz, yani
     periyot 50 µs — bu bekleme en kötü durumda %8, ISR'ı tıkamıyor. */
  delayMicroseconds(PULSE_US);
  PORTB &= ~PIN_STEP_MASK;
}

/* Bu tick'in adımlarını tick'in ilk %90'ına eşit aralıkla yay.
   Tam 1 ms'e yaysaydık son darbe bir sonraki tick ile aynı ana denk gelirdi;
   o tick stepsLeft'i ezer ve o adım sessizce kaybolurdu. %90'a sıkıştırınca
   adımlar 0.9 ms'te biter, 0.1 ms boşluk kalır. */
static inline void scheduleSteps(int16_t delta) {
  if (stepsLeft) clips++;              /* önceki tick bitmemiş: adım kaybı */

  if (delta == 0) { stepsLeft = 0; TIMSK1 &= ~_BV(OCIE1A); return; }

  if (delta > 0) { dirSign =  1; PORTB |=  PIN_DIR_MASK; }
  else           { dirSign = -1; PORTB &= ~PIN_DIR_MASK; }

  uint16_t n = (delta > 0) ? delta : -delta;
  /* Timer1 ön bölme 8 → 2 MHz → 0.9 ms = 1800 sayım. */
  uint16_t ocr = (uint16_t)(1800UL / n);
  if (ocr < 20) ocr = 20;              /* 10 µs alt sınır: ISR'a yer bırak */
  stepsLeft = n;
  TCNT1  = 0;
  OCR1A  = ocr - 1;
  TIFR1  = _BV(OCF1A);                 /* bekleyen bayrağı temizle */
  TIMSK1 |= _BV(OCIE1A);
}

/* ======================= 1 kHz tick (Timer2) ======================= */

ISR(TIMER2_COMPA_vect) {
  int32_t want = targetPos;

  switch (mode) {
    case M_IDLE:
      want = position;
      break;

    case M_JOG:
      posQ8 += velQ8;
      want = posQ8 >> 8;
      break;

    case M_GOTO: {
      posQ8 += velQ8;
      int32_t p = posQ8 >> 8;
      /* hedefi geçme */
      if ((velQ8 > 0 && p >= gotoTarget) || (velQ8 < 0 && p <= gotoTarget)) {
        p = gotoTarget; posQ8 = p << 8; mode = M_IDLE;
      }
      want = p;
      break;
    }

    case M_SINE: {
      if (sinAmp != sinAmpTgt) {
        int32_t d = sinAmpTgt - sinAmp;
        if (d >  sinAmpStep) d =  sinAmpStep;
        if (d < -sinAmpStep) d = -sinAmpStep;
        sinAmp += d;
      }
      if (sinAmp == 0 && sinAmpTgt == 0) {   /* yumuşak duruş tamamlandı */
        mode = M_IDLE; want = sinCentre; break;
      }
      sinPhase += sinInc;
      /* Tablo girişleri arasında ara değer. Doğrudan okumak yetmiyor: 256
         girişli tabloda faz, düşük frekanslarda tick başına ~1 giriş ilerliyor
         ve ara sıra 2 giriş atlıyor. 4 Hz'te 597 adım genlikte gerçek sinüsün
         tepe eğimi 15 adım/ms, ama atlanan girişte tek tick'te 29 adım
         isteniyor — hız tavanını aşıyor, kırpılıyor ve koşu, ortada gerçek bir
         sorun yokken şaibeli işaretleniyor. */
      {
        uint8_t  i  = (uint8_t)(sinPhase >> 24);
        uint16_t fr = (uint16_t)(sinPhase >> 8);
        int16_t  s0 = (int16_t)pgm_read_word(&SIN256[i]);
        int16_t  s1 = (int16_t)pgm_read_word(&SIN256[(uint8_t)(i + 1)]);
        int32_t  s  = (int32_t)s0 + (((int32_t)(s1 - s0) * (int32_t)fr) >> 16);
        want = sinCentre + (int32_t)((s * sinAmp) >> 15);
      }
      break;
    }

    case M_STREAM: {
      if (rTail == rHead) {                 /* tampon boş */
        if (streamEnded) { mode = M_IDLE; want = position; break; }
        underruns++;                        /* SESSİZ HATA — sayılıyor */
        want = position;                    /* olduğun yerde kal */
        break;
      }
      want = (int32_t)ring[rTail];
      rTail = (rTail + 1) & BUF_MASK;
      if (streamLeft != 0xFFFFFFFFUL && streamLeft > 0) {
        streamLeft--;
        if (streamLeft == 0) streamEnded = true;
      }
      break;
    }
  }

  /* Yazılım sınırı. Kırpınca JOG/GOTO'nun biriktirdiği kesirli konumu da geri
     çekiyoruz: yoksa sınıra dayanıp beklerken posQ8 dışarı doğru birikmeye devam
     eder, ters yöne bastığınızda tabla o birikmiş farkı yiyene kadar hiç
     kımıldamaz — kullanıcı "sıkıştı" sanır. */
  bool clamped = false;
  if (want < limMin) { want = limMin; clips++; clamped = true; }
  if (want > limMax) { want = limMax; clips++; clamped = true; }
  if (clamped && (mode == M_JOG || mode == M_GOTO)) posQ8 = want << 8;

  int32_t d = want - position;
  if (d >  MAX_STEPS_PER_TICK) { d =  MAX_STEPS_PER_TICK; clips++; }
  if (d < -MAX_STEPS_PER_TICK) { d = -MAX_STEPS_PER_TICK; clips++; }

  targetPos = want;
  scheduleSteps((int16_t)d);
}

/* ======================= kurulum ======================= */

static void timersInit() {
  /* Timer1: CTC, ön bölme 8. Kesme, adım gerektiğinde açılıyor. */
  TCCR1A = 0;
  TCCR1B = _BV(WGM12) | _BV(CS11);
  TIMSK1 = 0;

  /* Timer2: CTC, ön bölme 128 → 125 kHz; OCR2A=124 → tam 1000 Hz. */
  TCCR2A = _BV(WGM21);
  TCCR2B = _BV(CS22) | _BV(CS20);
  OCR2A  = (F_CPU / 128 / TICK_HZ) - 1;
  TIMSK2 = _BV(OCIE2A);
}

void setup() {
  DDRB  |= PIN_STEP_MASK | PIN_DIR_MASK;
  PORTB &= ~(PIN_STEP_MASK | PIN_DIR_MASK);
  Serial.begin(BAUD_RATE);
  timersInit();
  Serial.println(F("K shaker 1.0 tick=1000 steps_per_mm=80"));
}

/* ======================= komut ayrıştırma ======================= */

static char line[48];
static uint8_t lineLen = 0;

/* İkili kip: D<n> görüldüğünde tam olarak 2*n bayt okunur, sonra satır kipine
   dönülür. Ayrıştırıcı hiçbir zaman "acaba bu veri mi komut mu" durumunda
   kalmaz; bu yüzden dalga formunun içindeki '!' baytı acil dur sanılmaz. */
static uint16_t binLeft = 0;
static uint8_t  binHi   = 0;
static bool     binPhase = false;

static void stopAll(bool flush) {
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    mode = M_IDLE;
    stepsLeft = 0;
    velQ8 = 0;
    TIMSK1 &= ~_BV(OCIE1A);
    posQ8 = position << 8;
    targetPos = position;
    if (flush) { rHead = rTail = 0; streamLeft = 0; streamEnded = true;
                 streamArmed = false; binLeft = 0; binPhase = false; }
  }
}

static uint8_t bufFree() {
  uint8_t h, t;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { h = rHead; t = rTail; }
  return (uint8_t)(BUF_N - 1 - ((h - t) & BUF_MASK));
}

static void sendStatus() {
  int32_t p, tg; uint8_t m; uint16_t u, c;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { p = position; tg = targetPos; m = mode; u = underruns; c = clips; }
  Serial.print(F("S ")); Serial.print(p);
  Serial.print(' ');     Serial.print(m);
  Serial.print(' ');     Serial.print(bufFree());
  Serial.print(' ');     Serial.print(u);
  Serial.print(' ');     Serial.print(c);
  Serial.print(' ');     Serial.println(tg);
}

static long arg(char *&p) {
  while (*p == ' ') p++;
  long v = strtol(p, &p, 10);
  return v;
}

static void handleLine(char *s) {
  char c = s[0];
  char *p = s + 1;

  switch (c) {
    case '?': sendStatus(); return;

    case 'H':
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { position = 0; targetPos = 0; posQ8 = 0; sinCentre = 0; }
      Serial.println(F("K home")); return;

    case 'L': {
      long a = arg(p), b = arg(p);
      if (a >= b) { Serial.println(F("E limit min>=max")); return; }
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { limMin = a; limMax = b; }
      Serial.println(F("K limit")); return;
    }

    case 'J': {
      long v = arg(p);
      if (v > 20000L || v < -20000L) { Serial.println(F("E jog hiz siniri 20000")); return; }
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        posQ8 = position << 8;
        velQ8 = (v << 8) / TICK_HZ;
        mode  = (v == 0) ? M_IDLE : M_JOG;
      }
      Serial.println(F("K jog")); return;
    }

    case 'G': {
      long tgt = arg(p), sp = arg(p);
      if (sp <= 0 || sp > 20000L) { Serial.println(F("E goto hiz")); return; }
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        posQ8 = position << 8;
        gotoTarget = tgt;
        long dir = (tgt >= position) ? 1 : -1;
        velQ8 = ((dir * sp) << 8) / TICK_HZ;
        mode = M_GOTO;
      }
      Serial.println(F("K goto")); return;
    }

    case 'N': {
      long fmHz = arg(p), amp = arg(p);
      if (fmHz < 0 || fmHz > 200000L) { Serial.println(F("E sinus frekans")); return; }
      if (amp  < 0 || amp  > 30000L)  { Serial.println(F("E sinus genlik")); return; }
      /* Genlik 0: yumuşak duruş. Sinüs çalışmıyorsa yapacak bir şey yok. */
      if (fmHz == 0 || amp == 0) {
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
          if (mode == M_SINE) {
            sinAmpTgt = 0;
            sinAmpStep = sinAmp / AMP_RAMP_TICKS; if (sinAmpStep < 1) sinAmpStep = 1;
          } else {
            mode = M_IDLE;
          }
        }
        Serial.println(F("K sinus dur")); return;
      }
      /* faz artışı: 2^32 birim = 1 tur. inc = 2^32 * f / TICK_HZ, f milihertz */
      uint32_t inc = (uint32_t)((4294967296.0 * (double)fmHz) / (1000.0 * (double)TICK_HZ));
      if (inc == 0) inc = 1;
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        if (mode != M_SINE) {           /* baştan başlıyor: merkezi ve fazı kur */
          sinCentre = position; sinPhase = 0; sinAmp = 0;
        }
        /* Zaten sinüsteyse merkez ve faz KORUNUYOR. Her komutta merkezi o anki
           konuma çekseydik, çalışırken frekansı değiştirmek tablayı sinüsün o
           anki değeri kadar öteler ve tabla tarama boyunca yürürdü. */
        sinInc = inc;
        sinAmpTgt = amp;
        int32_t d = amp - sinAmp; if (d < 0) d = -d;
        sinAmpStep = d / AMP_RAMP_TICKS; if (sinAmpStep < 1) sinAmpStep = 1;
        mode = M_SINE;
      }
      Serial.println(F("K sinus")); return;
    }

    case 'R': {
      long n = arg(p);
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        rHead = rTail = 0;
        underruns = 0; clips = 0;
        streamLeft = (n <= 0) ? 0xFFFFFFFFUL : (uint32_t)n;
        streamEnded = false;
        posQ8 = position << 8;
        /* Dalga formu ön tampondan kısaysa eşik onun boyu olur; yoksa akış
           hiç başlamaz, çünkü tampon o eşiğe hiçbir zaman ulaşamaz. */
        primeN = (n > 0 && n < PRIME_N) ? (uint8_t)n : PRIME_N;
        mode = M_IDLE;              /* tampon dolana kadar bekle */
        streamArmed = true;
      }
      Serial.print(F("K stream ")); Serial.println(bufFree()); return;
    }

    case 'D': {
      long n = arg(p);
      if (n <= 0 || n > 64) { Serial.println(F("E chunk 1..64")); return; }
      if (n > bufFree())    { Serial.println(F("E chunk tampon dolu")); return; }
      binLeft = (uint16_t)(n * 2);
      binPhase = false;
      return;                       /* onay yok: veri hemen geliyor */
    }

    case 'X': stopAll(false); Serial.println(F("K stop")); return;
    case '!': stopAll(true);  Serial.println(F("K estop")); return;

    default:
      Serial.print(F("E bilinmeyen ")); Serial.println(c); return;
  }
}

/* ======================= ana döngü ======================= */

static uint32_t lastStatus = 0;
static uint32_t lastByte   = 0;

void loop() {
  while (Serial.available()) {
    uint8_t b = Serial.read();
    lastByte = millis();

    if (binLeft) {                         /* ikili veri kipi */
      if (!binPhase) { binHi = b; binPhase = true; }
      else {
        int16_t v = (int16_t)((uint16_t)binHi | ((uint16_t)b << 8));
        binPhase = false;
        uint8_t h;
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { h = rHead; }
        uint8_t nh = (uint8_t)((h + 1) & BUF_MASK);
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
          if (nh != rTail) { ring[h] = v; rHead = nh; }
          else             { clips++; }     /* taşma: kredi ihlali */
        }
      }
      binLeft--;
      continue;
    }

    if (b == '\n' || b == '\r') {
      if (lineLen) { line[lineLen] = 0; handleLine(line); lineLen = 0; }
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = (char)b;
    } else {
      lineLen = 0;                          /* çöp satır, at */
      Serial.println(F("E satir uzun"));
    }
  }

  uint32_t now = millis();

  /* Yarım kalmış ikili paket: 'D 10' dedi, 20 bayt yerine 15 gönderdi. Zaman
     aşımı olmasa ayrıştırıcı sonsuza kadar 16. baytı bekler ve kart hiçbir
     komuta cevap vermez — "kart kilitlendi" gibi görünür, oysa sadece söz
     kesilmiştir. */
  if (binLeft && (now - lastByte) > 200) {
    binLeft = 0; binPhase = false;
    Serial.println(F("E ikili paket yarim kaldi"));
  }

  /* Ön tampon doldu mu — akışı ancak o zaman başlat. */
  if (streamArmed) {
    uint8_t h, t;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { h = rHead; t = rTail; }
    uint8_t used = (uint8_t)((h - t) & BUF_MASK);
    bool done;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { done = streamEnded; }
    if (used >= primeN || done) {
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { mode = M_STREAM; streamArmed = false; }
      Serial.println(F("K basladi"));
    }
  }

  if (now - lastStatus >= 50) { lastStatus = now; sendStatus(); }
}
