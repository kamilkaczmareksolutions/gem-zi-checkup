# Rekomendacja końcowa — GEM na IKE

## Stan portfela
- Kapitał: 0 PLN
- Obecny koszyk: U5 (CNDX.L, EIMI.L, IWDA.L, IB01.L, CBU0.L)
- Obecnie wygrywający ETF: EIMI.L

## 1. Broker: BOSSA IKE (promo)

Przy kapitale 0 PLN, najlepszy wynik końcowy daje BOSSA IKE (promo) (XTB IKE=427719 PLN, BOSSA IKE (promo)=515817 PLN, mBank IKE (eMakler)=495752 PLN).

### Porównanie modeli kosztowych

| Broker | FX/leg | Prowizja | Frakcje | Uwagi |
|--------|--------|----------|---------|-------|
| XTB IKE | 0.5% | 0% | Tak | Wysoki FX, brak cash drag |
| BOSSA IKE (promo) | 0% | 0% (promo) | Nie | Subkonta walutowe, promo do 2027 |
| mBank IKE (eMakler) | 0.1% | 0% (stale) | Nie | Brak subkont walutowych, FX na obu nogach rotacji |

### Warunki migracji
- BOSSA IKE (promo) > XTB od kapitału ~5,000 PLN
- mBank IKE (eMakler) > XTB od kapitału ~5,000 PLN

## Benchmark: IWDA.L (pasywny DCA)
- XIRR: 12.27%
- MaxDD: -20.23%
- Wartość końcowa: 470,059 PLN

## 2. Optymalny deadband

**Wynik: deadband = 0.054 (5.4%)** (jednakowy dla wszystkich brokerów)

### Jak obliczono:
1. **Broker referencyjny**: BOSSA IKE (promo) (najtańszy IKE — najniższe tarcia kosztowe)
2. **IS optymalny** (informacyjnie): 0.068 (6.8%) — górna granica rozsądnego deadbandu;
najwyższy excess XIRR spośród deadbandów, których MaxDD nie przekracza MaxDD benchmarku + 10% margin.
Nie używany bezpośrednio do rekomendacji — podatny na look-ahead bias.
3. **OOS średnia** (walk-forward): 0.056 (5.6%)
4. **OOS mediana** (walk-forward): 0.053 (5.3%)
5. **Rekomendowany deadband** = 0.0530
   → zaokrąglony do siatki: **0.054 (5.4%)**

### Wyniki per broker @ deadband = 0.054

| Broker | Excess XIRR | MaxDD | Sharpe (IS) |
|--------|-------------|-------|--------|
| XTB IKE | +4.51% | -22.25% | 1.47 |
| BOSSA IKE (promo) | +5.40% | -21.40% | 1.49 |
| mBank IKE (eMakler) | +5.18% | -21.48% | 1.49 |

## 3. Uniwersum ETF

Rekomendowane: **U5**
U5 (5 ETF-ów): Sharpe=1.50, XIRR=17.98% (testowane przy IS deadband=6.8%)

**Przy rekomendowanym deadband=5.4% (OOS):** U5(5 ETF-ów): Sharpe=1.49, XIRR=17.67%

## 4. Walidacja Out-of-Sample

Średni OOS return per fold (skumulowany, 2-letni): 30.68%. Annualizowany: 14.31%
Wybrane deadbandy per fold: ['0.050', '0.052', '0.054', '0.068']

## 5. Scenariusze z regularnymi wpłatami (kapitał startowy = 0, CPI rewaloryzacja)

Wpłaty co miesiąc, rewaloryzowane o wskaźnik średniorocznej inflacji CPI (GUS) na początku każdego roku.
Kapitał startowy = 0 PLN.

### Wartość końcowa portfela

|   wpłata bazowa (PLN/mies.) |   bossa_ike_promo |   bossa_ike_standard |   mbank_ike |   taxed_account |   xtb_ike |
|----------------------------:|------------------:|---------------------:|------------:|----------------:|----------:|
|                         500 |           278,038 |              259,085 |     273,710 |         234,536 |   268,961 |
|                        1000 |           573,722 |              540,007 |     564,323 |         469,073 |   537,922 |
|                        2000 |         1,157,599 |            1,096,133 |   1,138,800 |         938,144 | 1,075,843 |

### Suma wpłat i rewaloryzacja

| Wpłata bazowa | Wpłata końcowa (po CPI) | Suma wpłat |
|:---:|:---:|:---:|
| 500 PLN | 783 PLN | 88,818 PLN |
| 1000 PLN | 1566 PLN | 177,635 PLN |
| 2000 PLN | 3133 PLN | 355,270 PLN |


## Podsumowanie decyzji

1. **Wybierz brokera** wg powyższej tabeli kosztowej i progu crossover.
2. **Ustaw deadband** na **5.4%**.
3. **Rozważ rozszerzenie koszyka** jeśli dane OOS to potwierdzają.
4. **Regularnie wpłacaj** — nawet małe kwoty znacząco podnoszą wartość końcową dzięki procentowi składanemu w parasolu IKE.
