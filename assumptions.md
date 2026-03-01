# Założenia symulacji GEM na IKE

## Źródło danych
- Dane: Yahoo Finance (Adjusted Close), uwzględniające splity i dywidendy.
- Częstotliwość: miesięczna (ostatni dzień roboczy miesiąca).
- Okres: najdłuższy wspólny zakres dostępnych danych dla danego uniwersum.

## Momentum
- Okno: pełne 12 miesięcy zwrotu z pominięciem ostatniego miesiąca (13-1), zgodne z literaturą akademicką.
- Formuła: `Momentum(e_i) = AdjClose[t-1] / AdjClose[t-13] - 1`.
- Numerator = cena sprzed 1 miesiąca, denominator = cena sprzed 13 miesięcy. Mierzona stopa zwrotu obejmuje pełne 12 miesięcy (od t-13 do t-1).

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
- Subkonta walutowe: tak (USD, EUR, GBP). Handel w tej samej walucie bez kosztu FX przy rotacjach.
- Przewalutowanie wpłat: 0.1% (PLN→USD). BOSSA daje 3 darmowe konwersje/rok, ale przy miesięcznych wpłatach pozostałe 9 konwersji jest płatnych.
- Akcje ułamkowe: niedostępne (pełne jednostki, reszta jako cash drag).
- Podatek: 0% (parasol IKE).
- Slippage: 0.1%.
- Źródło: [BOSSA IKE](https://bossa.pl/oferta/IKE-i-IKZE)

### mBank IKE (eMakler)
- Prowizja: 0% na ETF zagraniczne (stały element oferty, nie promocja).
- Przewalutowanie: 0.1% na konwersję (per leg). Brak subkont walutowych — przy sprzedaży ETF-a środki wracają do PLN, przy zakupie ponowna konwersja.
- Akcje ułamkowe: niedostępne (pełne jednostki, reszta jako cash drag).
- Podatek: 0% (parasol IKE).
- Slippage: 0.1%.
- Kluczowa różnica vs BOSSA: mBank nalicza FX na obu nogach rotacji (sell→PLN→buy), BOSSA promo z subkontami walutowymi unika FX przy rotacjach w ramach jednej waluty.
- Źródło: [mBank IKE eMakler](https://www.mbank.pl/indywidualny/inwestycje-i-oszczednosci/emerytura/ike-emakler/)

### Konto opodatkowane (benchmark)
- FX na rotacjach: 0% (sprzedaż i zakup w tej samej walucie, np. USD→USD).
- FX na wpłatach: 0.2% (PLN→USD via Walutomat).
- Podatek: 19% od zrealizowanego zysku (podatek Belki).
- Akcje ułamkowe: dostępne.
- Slippage: 0.1%.

## Deadband
- Próg nieczułości: algorytm zmienia ETF tylko gdy momentum nowego kandydata przewyższa obecny o co najmniej Delta punktów procentowych.
- Deadband chroni przed whipsawingiem i kompensuje koszty transakcyjne.
- Zakres testów: 0.0% do 8.0% co 0.2 pp.
- Wariant dynamiczny: `Delta = base + k * sigma(6m)`.
- Wybór optymalnego: **mediana OOS** — IS optimum (informacyjnie, z constraint MaxDD <= benchmark + 10% margin, oceniany na najtańszym brokerze IKE) wyznacza górną granicę. Rekomendowany deadband = mediana deadbandów wybranych per fold OOS w walk-forward, zaokrąglona do siatki. Jeden deadband dla wszystkich brokerów.

## Walk-Forward
- Okno treningowe: 60 miesięcy (5 lat).
- Okno testowe: 24 miesiące.
- Krok: 24 miesiące (brak nakładania się okien testowych).
- Ewaluacja OOS: TWR bez wpłat (contribution_schedule=None, initial_capital = wartość equity na początku okna OOS). Eliminuje zniekształcenie metryk przez harmonogram cashflow.

## Ograniczenia symulacji
- Brak modelowania wpływu na rynek (market impact) — uzasadnione małym portfelem.
- Ceny wykonania = adjusted close na koniec okresu (brak intraday).
- Brak modelowania ryzyka walutowego PLN/USD (ETF-y wyceniane w USD/EUR).
- BOSSA: 3 darmowe konwersje FX/rok nie są modelowane indywidualnie; zamiast tego stosujemy stały deposit_fx_cost = 0.1% na każdą wpłatę PLN (konserwatywne uproszczenie zakładające miesięczne wpłaty).
