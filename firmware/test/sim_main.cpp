/* shaker.ino'yu bilgisayarda çalıştıran koşum takımı.
 *
 * Neden: bu firmware'de yanlış giden şeylerin çoğu karta bakarak anlaşılmıyor.
 * "Tabla sınıra dayandı, geri basıyorum, kımıldamıyor" ya da "koşunun ortasında
 * durdu" gibi belirtiler, ancak tick tick izlenirse sebebe bağlanabiliyor.
 * Burada AVR yazmaçları ve Serial taklit ediliyor, Timer2 tick'i ile Timer1
 * darbe kesmesi elle sürülüyor; böylece bütün mantık gerçek zamanlı donanım
 * olmadan, tekrarlanabilir biçimde sınanabiliyor.
 *
 * Derle:  c++ -std=c++11 -O1 -o sim sim_main.cpp && ./sim
 */
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <string>
#include <deque>
#include <vector>
#include <cmath>

/* ---------------- AVR yazmaç taklidi ---------------- */
static uint8_t  PORTB, DDRB, TIMSK1, TIMSK2, TCCR1A, TCCR1B, TCCR2A, TCCR2B, TIFR1;
static uint16_t OCR1A, TCNT1;
static uint8_t  OCR2A;

#define _BV(b)   (1u << (b))
#define PB0 0
#define PB1 1
#define OCIE1A 1
#define OCF1A  1
#define WGM12  3
#define CS11   1
#define WGM21  1
#define CS22   2
#define CS20   0
#define OCIE2A 1
#define F_CPU  16000000L

#define PROGMEM
#define pgm_read_word(p) (*(p))
#define F(x) (x)
#define ISR(vec) void vec(void)
#define TIMER1_COMPA_vect timer1_isr
#define TIMER2_COMPA_vect timer2_isr

/* Kesme yokken tek iş parçacığı: ATOMIC_BLOCK boş bir kapsam. */
#define ATOMIC_BLOCK(x)
#define ATOMIC_RESTORESTATE

static uint32_t g_millis = 0;
static uint32_t millis() { return g_millis; }
static void delayMicroseconds(unsigned) {}

/* ---------------- Serial taklidi ---------------- */
struct FakeSerial {
  std::deque<uint8_t> rx;
  std::string tx;
  void begin(long) {}
  int  available() { return (int)rx.size(); }
  int  read() { if (rx.empty()) return -1; int v = rx.front(); rx.pop_front(); return v; }
  void print(const char *s)   { tx += s; }
  void print(char c)          { tx += c; }
  void print(long v)          { tx += std::to_string(v); }
  void print(int v)           { tx += std::to_string(v); }
  void print(unsigned v)      { tx += std::to_string(v); }
  void print(unsigned long v) { tx += std::to_string(v); }
  void println()              { tx += "\n"; }
  void println(const char *s) { tx += s; tx += "\n"; }
  void println(long v)        { tx += std::to_string(v); tx += "\n"; }
  void println(int v)         { tx += std::to_string(v); tx += "\n"; }
  void println(unsigned v)    { tx += std::to_string(v); tx += "\n"; }
  void println(char c)        { tx += c; tx += "\n"; }
  void feed(const std::string &s) { for (unsigned char c : s) rx.push_back(c); }
  void feedByte(uint8_t b)        { rx.push_back(b); }
  std::string take() { std::string s = tx; tx.clear(); return s; }
} Serial;

#include "../shaker/shaker.ino"

/* ---------------- koşum ---------------- */
static int fails = 0;
static void ok(bool c, const char *msg, const std::string &got = "") {
  if (!c) fails++;
  printf("%s%s%s%s\n", c ? "  ok  " : "FAIL  ", msg,
         got.empty() ? "" : "   -> ", got.c_str());
}
static std::string S(long v) { return std::to_string(v); }

/* Bir tick: Timer2 ISR, sonra o tick için kurulan darbelerin hepsi. */
static void tick() {
  timer2_isr();
  int guard = 0;
  while (stepsLeft && (TIMSK1 & _BV(OCIE1A)) && ++guard < 1000) timer1_isr();
  g_millis++;
  loop();                      /* seri alım + zamanlayıcılar */
}
static void ticks(int n) { for (int i = 0; i < n; i++) tick(); }

static void cmd(const std::string &s) { Serial.feed(s + "\n"); loop(); }

int main() {
  setup();
  Serial.take();

  /* ---- 1. temel: sıfırla, sınır koy ---- */
  cmd("H");
  cmd("L -4000 4000");
  ok(position == 0, "H konumu sifirliyor", S(position));
  ok(limMin == -4000 && limMax == 4000, "L sinirlari kuruyor");

  /* ---- 2. GOTO tam konuma gidiyor ---- */
  cmd("G 800 4000");            /* 800 adim, 4000 adim/s -> 200 ms */
  ticks(400);
  ok(position == 800, "GOTO tam 800 adimda duruyor", S(position));
  ok(mode == M_IDLE, "GOTO bitince IDLE", S(mode));

  /* 800 adim = 10 mm. Adim sayisi konumu tanimliyor, tahmin degil. */
  ok(std::abs(position * 0.0125 - 10.0) < 1e-9, "800 adim = 10.000 mm");

  /* ---- 3. JOG hizi dogru mu ---- */
  cmd("H"); cmd("J 2000");      /* 2000 adim/s */
  ticks(500);                   /* 0.5 s -> 1000 adim */
  ok(std::abs(position - 1000) <= 2, "JOG 2000 adim/s * 0.5 s = 1000", S(position));
  cmd("J 0"); ticks(2);
  ok(mode == M_IDLE, "J 0 duruyor");

  /* ---- 4. SINIRA DAYANIP GERI DONME  (gercek bir hataydi) ----
     Sinira bastir, orada bir sure bekle, sonra ters yone bas. Tabla DERHAL
     donmeli. posQ8 senkronlanmasaydi biriken fark kadar olu bosluk olurdu. */
  cmd("H"); cmd("L -1000 1000");
  cmd("J 8000"); ticks(400);                  /* sinira daya, 200 tick bekle */
  ok(position == 1000, "sinirda duruyor", S(position));
  long clipsAtLimit = clips;
  cmd("J -8000");
  ticks(5);                                   /* 5 ms icinde donmeli */
  ok(position < 1000, "sinirdan DERHAL geri donuyor (olu bosluk yok)", S(position));
  ok(clipsAtLimit > 0, "sinir kirpmasi sayiliyor", S(clipsAtLimit));
  cmd("X");

  /* ---- 5. SINUS frekansi ---- */
  cmd("H"); cmd("L -100000 100000");
  cmd("N 5000 400");                          /* 5.000 Hz, 400 adim genlik */
  ticks(500);                                 /* genlik rampasi otursun */
  std::vector<long> tr;
  for (int i = 0; i < 1000; i++) { tick(); tr.push_back(position); }
  long pk = 0; for (long v : tr) pk = std::max(pk, std::labs(v));
  ok(std::labs(pk - 400) <= 12, "sinus genligi 400 adim", S(pk));
  /* Cevrim sayisi degil, cevrimler ARASI mesafe olculuyor. Sayim, sinusun
     fazdan basladigi ilk gecisi kacirdigi icin hep bir eksik cikiyor; asil
     merak edilen zaten frekans hatasi, o da periyottan okunuyor.
     5 Hz, 1 kHz tick -> periyot tam 200 tick olmali. */
  std::vector<size_t> zc;
  for (size_t i = 1; i < tr.size(); i++) if (tr[i-1] < 0 && tr[i] >= 0) zc.push_back(i);
  ok(zc.size() >= 4, "sifir gecisleri bulundu", S((long)zc.size()));
  double per = (double)(zc.back() - zc.front()) / (double)(zc.size() - 1);
  char b[64]; snprintf(b, sizeof b, "%.3f tick", per);
  ok(std::fabs(per - 200.0) < 0.5, "5 Hz periyodu 200 tick (frekans hatasi <%%0.25)", b);
  /* ---- 5b. CANLI AYAR: frekansi degistirince merkez KAYMAMALI ----
     Tarama sirasinda frekans surekli degisiyor. Her komut merkezi o anki
     konuma cekseydi tabla tarama boyunca yavasca yururdu. */
  long centre0 = sinCentre;
  for (int f = 5000; f <= 25000; f += 2000) { cmd("N " + S(f) + " 400"); ticks(120); }
  ok(sinCentre == centre0, "frekans suprulurken merkez SABIT kaldi",
     S(sinCentre) + " / basta " + S(centre0));
  cmd("N 25000 0"); ticks(600);               /* yumusak dur */
  ok(std::labs(position - centre0) <= 4, "durunca merkeze donuyor, yurumedi",
     S(position - centre0));
  ok(mode == M_IDLE, "genlik sifira inince IDLE", S(mode));

  /* ---- 5c. CALISIRKEN GENLIK DEGISTIRME ----
     Asil sicrama riski burada. Konum = merkez + genlik*sin(faz). Sinusun
     tepesindeyken genligi 120 -> 150 adim yapmak, genlik aninda degisseydi
     tek tick'te 30 adimlik bir otelemedir; tavan 20. Rampa bunu yayiyor. */
  /* 20 Hz'te 100 adim genlik -> 12.6 adim/ms. Tavana (20) fazla yaklasmamak
     gerekiyor: sinus tablasindan gelen yuvarlama artiklari, sinusun tepe
     egiminin uzerine +-1 adim biniyor. 150 adim (18.9 adim/ms) sectigimizde
     bu artiklar tek tuk 21'e tasiyor ve kirpma sayaci artiyor. */
  cmd("H"); cmd("N 20000 100"); ticks(600);
  clips = 0;
  long jump = 0, prev = position;
  for (int k = 0; k < 6; k++) {
    cmd("N 20000 " + S(k % 2 ? 100 : 130));   /* calisirken ileri geri degistir */
    for (int i = 0; i < 300; i++) {
      tick(); jump = std::max(jump, std::labs(position - prev)); prev = position;
    }
  }
  ok(jump <= MAX_STEPS_PER_TICK, "genlik degisirken tek tick'te tavan asilmadi", S(jump));
  ok(clips == 0, "genlik rampasi KIRPMA URETMIYOR", S((long)clips));
  cmd("N 20000 0"); ticks(600);

  /* ---- 6. AKIS: mutlak konum, on tampon, underrun ---- */
  cmd("H");
  const int N = 300;
  std::vector<int16_t> wave(N);
  for (int i = 0; i < N; i++) wave[i] = (int16_t)lround(300 * sin(2 * M_PI * i / 100.0));

  cmd("R " + S(N));
  ok(mode == M_IDLE && streamArmed, "R sonrasi HENUZ baslamiyor (on tampon bekliyor)");
  ticks(30);
  ok(underruns == 0, "bos tamponda bekleme underrun SAYILMIYOR", S(underruns));

  /* parca parca besle, her seferinde bosluk kadar */
  int sent = 0;
  const uint32_t t_start = g_millis;
  while (sent < N || mode == M_STREAM || streamArmed) {
    int room = bufFree(); if (room > 64) room = 64;
    int n = std::min(room, N - sent);
    if (n > 0) {
      Serial.feed("D " + S(n) + "\n");
      for (int i = 0; i < n; i++) {
        Serial.feedByte((uint8_t)(wave[sent + i] & 0xFF));
        Serial.feedByte((uint8_t)((wave[sent + i] >> 8) & 0xFF));
      }
      sent += n;
    }
    loop();
    ticks(20);
    if (g_millis - t_start > 5000) break;   /* mutlak degil, GORECE sinir:
        onceki bolumler g_millis'i zaten binlerce tick ilerletmis oluyor */
  }
  ok(sent == N, "butun ornekler gonderildi", S(sent));
  ok(underruns == 0, "akis boyunca UNDERRUN YOK", S(underruns));
  ok(position == wave[N-1], "son konum dalga formunun son ornegi",
     S(position) + " / " + S(wave[N-1]));
  ok(mode == M_IDLE, "akis bitince IDLE", S(mode));

  /* ---- 7. UNDERRUN gercekten yakalaniyor mu ---- */
  cmd("H"); cmd("R 0");                        /* suresiz akis */
  Serial.feed("D 64\n");
  for (int i = 0; i < 64; i++) { Serial.feedByte(0); Serial.feedByte(0); }
  loop(); ticks(10);
  ok(mode == M_STREAM, "suresiz akis basladi", S(mode));
  ticks(200);                                  /* veri gondermeden bekle */
  ok(underruns > 100, "veri kesilince UNDERRUN sayiliyor", S(underruns));
  cmd("!");
  ok(mode == M_IDLE && rHead == rTail, "! acil dur tamponu bosaltiyor");

  /* ---- 8. yarim kalan ikili paket kilitlemiyor ---- */
  Serial.feed("D 10\n");
  Serial.feedByte(1); Serial.feedByte(0);      /* 20 yerine 2 bayt */
  loop();
  ok(binLeft > 0, "ikili kip acildi");
  g_millis += 300; loop();
  ok(binLeft == 0, "200 ms sonra ikili kip birakiliyor (kart kilitlenmiyor)");
  Serial.take();
  cmd("?");
  ok(Serial.take().substr(0, 2) == "S ", "komutlara yeniden cevap veriyor");

  /* ---- 9. hiz sinirinin ustu kirpiliyor ve sayiliyor ---- */
  cmd("H"); cmd("L -100000 100000");
  clips = 0;
  cmd("R 0");
  Serial.feed("D 64\n");
  for (int i = 0; i < 64; i++) {               /* 1 ms'te 5000 adim istiyor */
    int16_t v = (int16_t)(i * 5000 > 30000 ? 30000 : i * 5000);
    Serial.feedByte((uint8_t)(v & 0xFF)); Serial.feedByte((uint8_t)(v >> 8));
  }
  loop(); ticks(70);
  ok(clips > 0, "asiri hiz KIRPILIYOR ve sayiliyor", S(clips));
  ok(position <= 70L * MAX_STEPS_PER_TICK, "kirpma gercekten uyguland1", S(position));
  cmd("!");

  printf(fails ? "\n%d KONTROL BASARISIZ\n" : "\nhepsi gecti\n", fails);
  return fails ? 1 : 0;
}
