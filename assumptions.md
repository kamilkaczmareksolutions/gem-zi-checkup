# Założenia symulacji GEM na IKE

## Źródło danych
- Dane: Yahoo Finance (Adjusted Close), uwzględniające splity i dywidendy.
- Częstotliwość: miesięczna (ostatni dzień roboczy miesiąca).
- Okres: najdłuższy wspólny zakres dostępnych danych dla danego uniwersum.

## Momentum
- Okno: 12 miesięcy z pominięciem ostatniego miesiąca (12-1), zgodne z literaturą akademicką.
- Formuła: `Momentum(e_i) = AdjClose[t-1] / AdjClose[t-12] - 1`.

## Alokacja
- 100% kapitału w jednym ETF-ie w danym momencie (strategia all-in).
- Filtr absolute momentum: jeśli najlepsze aktywo ryzykowne ma momentum < 0, przejdź do najlepszego aktywa bezpiecznego.

## Koszty transakcyjne

### XTB IKE
- Prowizja: 0% do 100 000 EUR obrotu miesięcznie.
- Przewalutowanie: 0.5% na każdej konwersji PLN<->USD (łącznie ~1.0% na rotację).
- Akcje ułamkowe: dostępne (100% kapitału zaalokowane).
- Podatek: 0% (parasol IKE).
- Slippage: 0.1% (konserwatywnie).
- Źródło: [XTB Help Center](https://www.xtb.com/int/help-center/stocks-and-etfs-10-1/is-there-a-currency-conversion-fee-when-trading-stocks-and-etfs-listed-in-other-currencies)

### BOSSA IKE
- Prowizja: 0% na ETF zagraniczne (promocja do końca lutego 2027). Standardowo: 0.29%, min 14 PLN.
- Subkonta walutowe: tak (USD, EUR, GBP). Handel w tej samej walucie bez kosztu FX.
- Akcje ułamkowe: niedostępne (pełne jednostki, reszta jako cash drag).
- Podatek: 0% (parasol IKE).
- Slippage: 0.1%.
- Źródło: [BOSSA IKE](https://bossa.pl/oferta/IKE-i-IKZE)

### Konto opodatkowane (benchmark)
- Jak XTB IKE, ale z 19% podatkiem od zrealizowanego zysku (podatek Belki).

## Deadband
- Próg nieczułości: algorytm zmienia ETF tylko gdy momentum nowego kandydata przewyższa obecny o co najmniej Delta punktów procentowych.
- Deadband chroni przed whipsawingiem i kompensuje koszty transakcyjne.
- Zakres testów: 0.0% do 6.0% co 0.25 pp.
- Wariant dynamiczny: `Delta = base + k * sigma(6m)`.

## Walk-Forward
- Okno treningowe: 60 miesięcy (5 lat).
- Okno testowe: 12 miesięcy.
- Krok: 12 miesięcy (brak nakładania się okien testowych).

## Ograniczenia symulacji
- Brak modelowania wpływu na rynek (market impact) — uzasadnione małym portfelem.
- Ceny wykonania = adjusted close na koniec okresu (brak intraday).
- Brak modelowania ryzyka walutowego PLN/USD (ETF-y wyceniane w USD/EUR).
- W BOSSA koszty 3 darmowych przewalutowań PLN->USD/rok nie są modelowane — zakładamy, że kapitał już rezyduje na subkoncie walutowym.
