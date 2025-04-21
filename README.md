# CryptoTax (more compatible with Binance export history)
Crypto P&amp;L and Tax for the Brazilian government

This script processes cryptocurrency transactions to calculate taxable gains and optionally mark-to-market (MTM) values using FIFO, LIFO, or HIFO accounting methods. It reads data from an Excel file containing trades, deposits, and purchases, then fetches daily USD-BRL exchange rates from Brazil’s Central Bank (PTAX). It standardizes all transactions into acquisitions and sales, adjusting values using FX rates and accounting for trading fees. For each asset, it tracks inventory over time, calculates average cost, and determines realized gains month by month. It then generates a monthly summary CSV with quantities bought, sold, remaining, total gains, and cost basis. If the --mtm flag is enabled, it also looks up historical price data for each asset near month-end, estimates the unrealized profit based on current value versus average cost, and outputs that to a separate MTM CSV.

**How to use it:**

To use this script, place your transaction data in an Excel file named Transacoes.xlsx in the same folder as the script. Create four sheets named exactly: trade, Compras, Depositos, and Depositos_BRL. The trade sheet must include Binance-style columns like Date(UTC), Base Asset, Quote Asset, Type, Price, Amount, Total, Fee, and Fee Coin. The Compras sheet should include Receive Amount and Spend Amount, while the Depositos and Depositos_BRL sheets include received crypto or BRL values. You may optionally add a Cost BRL column in Depositos to override automatic FX calculation.

**Sheets:**

**Sheet: trade**

Required columns (case-insensitive):

Date(UTC): Date and time of the trade.

Base Asset: The asset being bought or sold.

Quote Asset: The currency used to buy/sell (e.g., USDT).

Type: Either BUY or SELL.

Price: Unit price of the asset.

Amount: Quantity traded.

Total: Total quote amount.

Fee: Fee charged.

Fee Coin: Asset in which fee was charged.

**Sheet: Compras**
Purchases using BRL (e.g., via local exchanges).

**Required columns:**

Receive Amount: Format like 0.01 BTC.

Spend Amount: Format like 1000 BRL.

**Sheet: Depositos**
Crypto deposited into your wallet/exchange.

**Required columns:**

Data (UTC+0): Date of deposit.

Moeda: The crypto asset deposited.

Valor: Amount deposited.

Optional: Cost BRL — overrides FX calculation.

**Sheet: Depositos_BRL**
Fiat BRL deposits.

**Required columns:**

Data (UTC+0): Date of deposit.

Receive Amount: Format like 1000 BRL.
