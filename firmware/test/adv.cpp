/* Düşmanca sınamalar: firmware'i doğru kullanılmadığında ne yaptığı.
 * Normal akışı sim_main.cpp sınıyor; burada sadece kötü girdiler var. */
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <string>
#include <deque>
#include <vector>
#include <cmath>

static uint8_t  PORTB, DDRB, TIMSK1, TIMSK2, TCCR1A, TCCR1B, TCCR2A, TCCR2B, TIFR1;
static uint16_t OCR1A, TCNT1;
static uint8_t  OCR2A;
#define _BV(b) (1u << (b))
#define PB0 0
#define PB1 1
#define OCIE1A 1
#define OCF1A 1
#define WGM12 3
#define CS11 1
#define WGM21 1
#define CS22 2
#define CS20 0
#define OCIE2A 1
#define F_CPU 16000000L
#define PROGMEM
#define pgm_read_word(p) (*(p))
#define F(x) (x)
#define ISR(v) void v(void)
#define TIMER1_COMPA_vect timer1_isr
#define TIMER2_COMPA_vect timer2_isr
#define ATOMIC_BLOCK(x)
#define ATOMIC_RESTORESTATE
static uint32_t g_millis = 0;
static uint32_t millis() { return g_millis; }
static void delayMicroseconds(unsigned) {}
struct FakeSerial {
  std::deque<uint8_t> rx; std::string tx;
  void begin(long) {}
  int available() { return (int)rx.size(); }
  int read() { if (rx.empty()) return -1; int v = rx.front(); rx.pop_front(); return v; }
  void print(const char*s){tx+=s;} void print(char c){tx+=c;}
  void print(long v){tx+=std::to_string(v);} void print(int v){tx+=std::to_string(v);}
  void print(unsigned v){tx+=std::to_string(v);} void print(unsigned long v){tx+=std::to_string(v);}
  void println(){tx+="\n";} void println(const char*s){tx+=s;tx+="\n";}
  void println(long v){tx+=std::to_string(v);tx+="\n";}
  void println(int v){tx+=std::to_string(v);tx+="\n";}
  void println(unsigned v){tx+=std::to_string(v);tx+="\n";}
  void println(char c){tx+=c;tx+="\n";}
  void feed(const std::string&s){for(unsigned char c:s)rx.push_back(c);}
  void feedByte(uint8_t b){rx.push_back(b);}
  std::string take(){std::string s=tx;tx.clear();return s;}
} Serial;
#include "../shaker/shaker.ino"

static int fails=0;
static void ok(bool c,const char*m,const std::string&g=""){
  if(!c)fails++;
  printf("%s%s%s%s\n", c?"  ok  ":"FAIL  ", m, g.empty()?"":"   -> ", g.c_str());
}
static std::string S(long v){return std::to_string(v);}
static void tick(){ timer2_isr(); int gd=0;
  while(stepsLeft&&(TIMSK1&_BV(OCIE1A))&&++gd<2000) timer1_isr();
  g_millis++; loop(); }
static void ticks(int n){for(int i=0;i<n;i++)tick();}
static void cmd(const std::string&s){Serial.feed(s+"\n");loop();}
static std::string reply(const std::string&s){Serial.take();cmd(s);return Serial.take();}

int main(){
  setup(); Serial.take();

  // --- bozuk komutlar ---
  ok(reply("Z").substr(0,1)=="E", "bilinmeyen komut E doner", reply("Q"));
  ok(reply("L 100 100").substr(0,1)=="E", "min==max reddediliyor");
  ok(reply("L 500 -500").substr(0,1)=="E", "min>max reddediliyor");
  ok(reply("J 999999").substr(0,1)=="E", "asiri jog hizi reddediliyor");
  ok(reply("G 100 0").substr(0,1)=="E", "sifir goto hizi reddediliyor");
  ok(reply("G 100 -5").substr(0,1)=="E", "negatif goto hizi reddediliyor");
  ok(reply("N 999999 100").substr(0,1)=="E", "asiri sinus frekansi reddediliyor");
  ok(reply("N 5000 99999").substr(0,1)=="E", "asiri sinus genligi reddediliyor");
  ok(reply("D 0").substr(0,1)=="E", "sifir uzunluklu paket reddediliyor");
  ok(reply("D 999").substr(0,1)=="E", "cok buyuk paket reddediliyor");

  // --- bos ve cok uzun satir ---
  Serial.take(); cmd(""); ok(Serial.take().empty(), "bos satir sessizce yutuluyor");
  std::string longline(80,'A');
  ok(reply(longline).find("uzun")!=std::string::npos, "cok uzun satir bildiriliyor");
  ok(reply("?").substr(0,2)=="S ", "uzun satirdan sonra hala cevap veriyor");

  // --- tampon tasmasi: kredi ihlali ---
  cmd("H"); cmd("L -100000 100000"); cmd("R 0");
  clips = 0;
  for (int k=0;k<8;k++){                    // 8 x 64 = 512 ornek, tampon 255
    Serial.feed("D 64\n");
    for(int i=0;i<64;i++){Serial.feedByte(0);Serial.feedByte(0);}
    loop();
  }
  ok(true, "kredi ihlali cokme URETMIYOR");
  ok(bufFree() <= 255, "tampon sinirlarin icinde", S(bufFree()));

  // --- akis sirasinda X ---
  ticks(20);
  cmd("X");
  long p1 = position; ticks(50);
  ok(position==p1, "akis ortasinda X hemen durduruyor", S(position));

  // --- sinirin DISINDA baslayip iceri girme ---
  cmd("H"); cmd("L 100 200");               // konum 0, sinir 100..200
  ticks(30);
  ok(position>=100, "sinir disinda baslayinca iceri cekiliyor", S(position));

  // --- GOTO sinirin otesine ---
  cmd("L -1000 1000"); cmd("H");
  cmd("G 5000 8000"); ticks(1200);
  ok(position==1000, "GOTO sinirda duruyor, asmiyor", S(position));

  // --- ayni komutu ust uste yollamak ---
  cmd("H");
  for(int i=0;i<50;i++){ cmd("N 10000 200"); ticks(4); }
  ok(mode==M_SINE, "tekrar tekrar N gonderilince hala sinuste");
  ok(std::labs(sinCentre)<=2, "merkez kaymadi", S(sinCentre));
  cmd("X");

  // --- H akis sirasinda ---
  cmd("R 0");
  Serial.feed("D 64\n");
  for(int i=0;i<64;i++){int16_t v=(int16_t)(i*4);Serial.feedByte(v&0xFF);Serial.feedByte(v>>8);}
  loop(); ticks(70);
  cmd("H");
  ok(position==0, "akis sirasinda H konumu sifirliyor", S(position));
  cmd("!");

  // --- negatif ve uc int16 degerler ---
  cmd("H"); cmd("L -100000 100000"); cmd("R 4");
  Serial.feed("D 4\n");
  int16_t ext[4] = {32767, -32768, 0, 100};
  for(int i=0;i<4;i++){Serial.feedByte(ext[i]&0xFF);Serial.feedByte((ext[i]>>8)&0xFF);}
  loop(); ticks(400);
  ok(clips>0, "int16 uclari hiz tavaniyla kirpiliyor, cokmuyor", S((long)clips));
  cmd("!");

  printf(fails?"\n%d KONTROL BASARISIZ\n":"\nhepsi gecti\n", fails);
  return fails?1:0;
}
