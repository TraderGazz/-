#property strict

input bool UseMarketWatchSymbols = false;
input string Symbols = "EURUSD.str,GBPUSD.str,USDJPY.str,USDCHF.str,USDCAD.str,AUDUSD.str,NZDUSD.str,EURJPY.str,GBPJPY.str,EURGBP.str,AUDJPY.str,CADJPY.str,CHFJPY.str,XAUUSD.str,XAGUSD.str";

input bool ExportM1 = true;
input bool ExportM5 = true;
input bool ExportM15 = true;
input bool ExportH1 = true;
input bool ExportH4 = true;
input bool ExportD1 = true;
input bool ExportW1 = true;

input int BarsM1 = 10000;
input int BarsM5 = 10000;
input int BarsM15 = 10000;
input int BarsH1 = 5000;
input int BarsH4 = 3000;
input int BarsD1 = 2000;
input int BarsW1 = 1000;

input string OutDir = "mt5_feed";
input bool WriteHeartbeat = true;
input int TimerSeconds = 5;

string g_symbols[];
datetime g_last_m1 = 0;
datetime g_last_m5 = 0;
datetime g_last_h1 = 0;

string Trim(string s)
{
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

bool EnsureRootDir()
{
   if(StringLen(OutDir) == 0) return false;
   FolderCreate(OutDir);
   return true;
}

void EnsureSymbolDir(string symbol)
{
   FolderCreate(OutDir + "\\" + symbol);
}

void WriteHeartbeatNow()
{
   if(!WriteHeartbeat) return;
   string path = OutDir + "\\HEARTBEAT.txt";
   int h = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE) return;
   FileWriteString(h, IntegerToString((int)TimeGMT()));
   FileClose(h);
}

void ExportTf(string symbol, ENUM_TIMEFRAMES tf, int bars, string tf_name)
{
   MqlRates rates[];
   int copied = CopyRates(symbol, tf, 1, bars, rates); // closed bars only
   if(copied <= 0) return;
   ArraySetAsSeries(rates, true);

   EnsureSymbolDir(symbol);
   string path = OutDir + "\\" + symbol + "\\" + tf_name + ".csv";
   int h = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE) return;

   FileWriteString(h, "time_utc,open,high,low,close,volume\n");
   for(int i = copied - 1; i >= 0; i--)
   {
      string line = IntegerToString((int)rates[i].time) + ","
         + DoubleToString(rates[i].open, 8) + ","
         + DoubleToString(rates[i].high, 8) + ","
         + DoubleToString(rates[i].low, 8) + ","
         + DoubleToString(rates[i].close, 8) + ","
         + IntegerToString((int)rates[i].tick_volume) + "\n";
      FileWriteString(h, line);
   }
   FileClose(h);
}

void BuildSymbols()
{
   ArrayResize(g_symbols, 0);
   if(UseMarketWatchSymbols)
   {
      int n = SymbolsTotal(true);
      if(n <= 0) return;
      ArrayResize(g_symbols, n);
      for(int i=0;i<n;i++)
         g_symbols[i] = SymbolName(i, true);
      return;
   }

   int m = StringSplit(Symbols, ',', g_symbols);
   if(m <= 0) ArrayResize(g_symbols, 0);
}

void ExportAll()
{
   for(int i=0;i<ArraySize(g_symbols);i++)
   {
      string s = Trim(g_symbols[i]);
      if(StringLen(s)==0) continue;
      SymbolSelect(s, true);

      if(ExportM1) ExportTf(s, PERIOD_M1, BarsM1, "M1");
      if(ExportM5) ExportTf(s, PERIOD_M5, BarsM5, "M5");
      if(ExportM15) ExportTf(s, PERIOD_M15, BarsM15, "M15");
      if(ExportH1) ExportTf(s, PERIOD_H1, BarsH1, "H1");
      if(ExportH4) ExportTf(s, PERIOD_H4, BarsH4, "H4");
      if(ExportD1) ExportTf(s, PERIOD_D1, BarsD1, "D1");
      if(ExportW1) ExportTf(s, PERIOD_W1, BarsW1, "W1");
   }
   WriteHeartbeatNow();
}

int OnInit()
{
   if(!EnsureRootDir())
   {
      Print("BarFeedExporter: failed to create output dir ", OutDir);
      return INIT_FAILED;
   }
   BuildSymbols();
   if(ArraySize(g_symbols) <= 0)
   {
      Print("BarFeedExporter: no symbols");
      return INIT_FAILED;
   }
   ExportAll();
   EventSetTimer(MathMax(1, TimerSeconds));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   BuildSymbols();
   if(ArraySize(g_symbols) <= 0)
      return;
   ExportAll();
}

void OnTick()
{
   // OnTimer handles regular export cadence; keep OnTick as no-op fallback.
}
