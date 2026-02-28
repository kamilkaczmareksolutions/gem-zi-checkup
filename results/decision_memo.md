# Rekomendacja końcowa — GEM na IKE

## Stan portfela
- Kapitał: 9,000 PLN
- Obecny koszyk: U5 (CNDX.L, EIMI.L, IWDA.L, IB01.L, CBU0.L)
- Obecnie wygrywający ETF: EIMI.L

## 1. Broker: BOSSA IKE (promo)

Przy kapitale 9000 PLN, najlepszy wynik końcowy daje BOSSA IKE (promo) (XTB IKE=46236 PLN, BOSSA IKE (promo)=62157 PLN, mBank IKE (eMakler)=58265 PLN).

### Porównanie modeli kosztowych

| Broker | FX/leg | Prowizja | Frakcje | Uwagi |
|--------|--------|----------|---------|-------|
| XTB IKE | 0.5% | 0% | Tak | Wysoki FX, brak cash drag |
| BOSSA IKE (promo) | 0% | 0% (promo) | Nie | Subkonta walutowe, promo do 2027 |
| mBank IKE (eMakler) | 0.1% | 0% (stale) | Nie | Brak subkont walutowych, FX na obu nogach rotacji |

### Warunki migracji
- BOSSA IKE (promo) > XTB od kapitału ~5,000 PLN
- mBank IKE (eMakler) > XTB od kapitału ~5,000 PLN

## Benchmark: IWDA.L (pasywny buy-and-hold)
- CAGR: 11.72%
- MaxDD: -24.05%
- Wartość końcowa: 42,822 PLN

Reguła GEM: strategia ma sens tylko jeśli **MaxDD strategii <= MaxDD benchmarku**.
Optymalny deadband = najwyższy excess return nad benchmark spośród wariantów spełniających ten warunek.

## 2. Optymalny deadband

| Broker | Deadband | Excess CAGR |
|--------|----------|-------------|
| XTB IKE | 0.012 (1.2%) | +2.72% |
| BOSSA IKE (promo) | 0.068 (6.8%) | +6.36% |
| mBank IKE (eMakler) | 0.068 (6.8%) | +6.28% |

Kryterium wyboru: spośród deadbandów, których MaxDD nie przekracza MaxDD benchmarku,
wybierany jest ten z najwyższym excess CAGR (nadwyżką nad benchmark).

## 3. Uniwersum ETF

Rekomendowane: **U5_common**
U5_common (5 ETF-ów): Sharpe=0.97, CAGR=14.44%

## 4. Walidacja Out-of-Sample

Średni OOS return per fold: 12.65%. Średni wybrany deadband: 0.030.

## 5. Scenariusze z regularnymi wpłatami

|   monthly_contribution |   bossa_ike_promo |   bossa_ike_standard |   mbank_ike |   taxed_account |   xtb_ike |
|-----------------------:|------------------:|---------------------:|------------:|----------------:|----------:|
|                      0 |           77875.9 |              73113.4 |     77182.3 |         46032   |   51658.3 |
|                    500 |          119571   |             111048   |    116495   |         70150.1 |   78416.9 |
|                   1000 |          161044   |             149383   |    156685   |         94268.3 |  105175   |
|                   2000 |          243081   |             226597   |    237939   |        142505   |  158693   |

## Podsumowanie decyzji

1. **Wybierz brokera** wg powyższej tabeli kosztowej i progu crossover.
2. **Ustaw deadband** na poziomie wskazanym powyżej dla wybranego brokera.
3. **Rozważ rozszerzenie koszyka** jeśli dane OOS to potwierdzają.
4. **Regularnie wpłacaj** — nawet małe kwoty znacząco podnoszą wartość końcową dzięki procentowi składanemu w parasolu IKE.
