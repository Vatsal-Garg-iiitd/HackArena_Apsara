import type { Candle } from "@/lib/types";

export type OptionType = "call" | "put";

export type PricingInput = {
  S: number;
  K: number;
  r: number;
  sigma: number;
  T: number;
  option_type: OptionType;
  num_paths: number;
};

export type MethodPrediction = {
  price: number;
  confidence_interval?: [number, number];
};

export type HorizonPrediction = {
  horizon_days: number;
  methods: {
    monte_carlo: MethodPrediction;
    fosm: MethodPrediction;
    pem: MethodPrediction;
    taguchi: MethodPrediction;
  };
  average_price: number;
};

function erf(x: number) {
  const sign = x >= 0 ? 1 : -1;
  const abs = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * abs);
  const y =
    1 -
    (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) *
      t *
      Math.exp(-abs * abs);
  return sign * y;
}

function normalCdf(value: number) {
  return 0.5 * (1 + erf(value / Math.sqrt(2)));
}

function blackScholes({ S, K, r, sigma, T, option_type }: PricingInput) {
  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;

  if (option_type === "call") {
    return S * normalCdf(d1) - K * Math.exp(-r * T) * normalCdf(d2);
  }

  return K * Math.exp(-r * T) * normalCdf(-d2) - S * normalCdf(-d1);
}

function payoff(price: number, K: number, optionType: OptionType) {
  return optionType === "call" ? Math.max(price - K, 0) : Math.max(K - price, 0);
}

function seededNormal(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  const u1 = Math.max(x - Math.floor(x), 0.000001);
  const y = Math.sin((seed + 17) * 78.233) * 23454.123;
  const u2 = Math.max(y - Math.floor(y), 0.000001);
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

export function deriveAnnualVolatility(candles: Candle[]) {
  const closes = candles
    .map((candle) => candle.close)
    .filter((close): close is number => typeof close === "number" && Number.isFinite(close) && close > 0)
    .slice(-252);

  if (closes.length < 20) return null;

  const returns = closes.slice(1).map((close, index) => close / closes[index] - 1);
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const variance = returns.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / Math.max(returns.length - 1, 1);
  const sigma = Math.sqrt(variance) * Math.sqrt(252);

  return sigma > 0 ? sigma : null;
}

export function monteCarloPrice(input: PricingInput): MethodPrediction {
  const paths = Math.max(100, Math.min(input.num_paths, 100000));
  const drift = (input.r - 0.5 * input.sigma * input.sigma) * input.T;
  const diffusion = input.sigma * Math.sqrt(input.T);
  const payoffs: number[] = [];

  for (let index = 0; index < paths; index += 1) {
    const z = seededNormal(index + Math.round(input.S * 100));
    const terminalPrice = input.S * Math.exp(drift + diffusion * z);
    payoffs.push(payoff(terminalPrice, input.K, input.option_type));
  }

  const discounted = Math.exp(-input.r * input.T);
  const mean = payoffs.reduce((sum, value) => sum + value, 0) / paths;
  const variance = payoffs.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / Math.max(paths - 1, 1);
  const standardError = (Math.sqrt(variance) / Math.sqrt(paths)) * discounted;
  const price = mean * discounted;

  return {
    price,
    confidence_interval: [Math.max(0, price - 1.96 * standardError), price + 1.96 * standardError]
  };
}

export function fosmPrice(input: PricingInput): MethodPrediction {
  const base = blackScholes(input);
  const up = blackScholes({ ...input, S: input.S * 1.01 });
  const down = blackScholes({ ...input, S: input.S * 0.99 });
  const uncertainty = Math.abs(up - down) / 2;

  return {
    price: base,
    confidence_interval: [Math.max(0, base - uncertainty), base + uncertainty]
  };
}

export function pemPrice(input: PricingInput): MethodPrediction {
  const sigmaBump = Math.max(input.sigma * 0.1, 0.01);
  const values = [
    blackScholes(input),
    blackScholes({ ...input, S: input.S * 1.02 }),
    blackScholes({ ...input, S: input.S * 0.98 }),
    blackScholes({ ...input, sigma: input.sigma + sigmaBump }),
    blackScholes({ ...input, sigma: Math.max(input.sigma - sigmaBump, 0.0001) })
  ];
  const price = values.reduce((sum, value) => sum + value, 0) / values.length;
  const sd = Math.sqrt(values.reduce((sum, value) => sum + Math.pow(value - price, 2), 0) / values.length);

  return {
    price,
    confidence_interval: [Math.max(0, price - 1.96 * sd), price + 1.96 * sd]
  };
}

export function taguchiPrice(input: PricingInput): MethodPrediction {
  const levels = [
    { S: input.S * 0.99, sigma: input.sigma * 0.9 },
    { S: input.S * 0.99, sigma: input.sigma * 1.1 },
    { S: input.S * 1.01, sigma: input.sigma * 0.9 },
    { S: input.S * 1.01, sigma: input.sigma * 1.1 }
  ];
  const values = levels.map((level) => blackScholes({ ...input, S: level.S, sigma: level.sigma }));
  const price = values.reduce((sum, value) => sum + value, 0) / values.length;
  const sd = Math.sqrt(values.reduce((sum, value) => sum + Math.pow(value - price, 2), 0) / values.length);

  return {
    price,
    confidence_interval: [Math.max(0, price - 1.96 * sd), price + 1.96 * sd]
  };
}

export function predictHorizons(base: Omit<PricingInput, "T">, horizons = [1, 3, 7]): HorizonPrediction[] {
  return horizons.map((days) => {
    const input = { ...base, T: days / 365 };
    const methods = {
      monte_carlo: monteCarloPrice(input),
      fosm: fosmPrice(input),
      pem: pemPrice(input),
      taguchi: taguchiPrice(input)
    };
    const average_price =
      (methods.monte_carlo.price + methods.fosm.price + methods.pem.price + methods.taguchi.price) / 4;

    return {
      horizon_days: days,
      methods,
      average_price
    };
  });
}
