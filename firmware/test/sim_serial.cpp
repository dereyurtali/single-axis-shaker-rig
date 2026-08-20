/* shaker.ino'yu gerçek zamanlı bir seri cihaz gibi çalıştırır: stdin karta
 * giden hat, stdout karttan gelen hat.
 *
 * Amacı sim_main.cpp'den farklı. O, firmware'in mantığını tek başına sınıyor.
 * Bu ise masaüstü uygulamasıyla kartın BİRBİRİNİ anlayıp anlamadığını sınamak
 * için var: kredi hesabı, 'D' paketlerinin çerçevelenmesi, little-endian bayt
 * sırası, akışın gerçek zamanda underrun'sız yürüyüp yürümediği. Bunlar iki
 * tarafı ayrı ayrı doğrulayınca görünmeyen, sadece uçlar birleşince çıkan
 * hatalar.
 *
 * Derle:  c++ -std=c++11 -O2 -Istub -o sim_serial sim_serial.cpp
 * Kullan: python3 test_integration.py   (bunu kendi başlatır)
 */
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <string>
#include <deque>
#include <vector>
#include <cmath>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>

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
#define ATOMIC_BLOCK(x)
#define ATOMIC_RESTORESTATE

static uint32_t g_millis = 0;
static uint32_t millis() { return g_millis; }
static void delayMicroseconds(unsigned) {}

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
} Serial;

#include "../shaker/shaker.ino"

static double now_s() {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main() {
  fcntl(0, F_SETFL, O_NONBLOCK);
  setup();

  const double t0 = now_s();
  uint32_t ticks_done = 0;
  uint8_t inbuf[4096];

  for (;;) {
    ssize_t n = ::read(0, inbuf, sizeof inbuf);
    if (n > 0) for (ssize_t i = 0; i < n; i++) Serial.rx.push_back(inbuf[i]);
    else if (n == 0) break;                    /* hat kapandı */

    /* Duvar saatiyle 1 kHz: geride kalınmışsa açığı kapat. */
    uint32_t want = (uint32_t)((now_s() - t0) * 1000.0);
    while (ticks_done < want) {
      timer2_isr();
      int guard = 0;
      while (stepsLeft && (TIMSK1 & _BV(OCIE1A)) && ++guard < 1000) timer1_isr();
      g_millis++;
      ticks_done++;
      loop();
    }
    loop();

    if (!Serial.tx.empty()) {
      const std::string out = Serial.tx;
      Serial.tx.clear();
      size_t off = 0;
      while (off < out.size()) {
        ssize_t w = ::write(1, out.data() + off, out.size() - off);
        if (w <= 0) break;
        off += (size_t)w;
      }
    }
    usleep(200);
  }
  return 0;
}
