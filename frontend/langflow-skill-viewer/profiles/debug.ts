/** Opt-in at build time; the regular production build keeps password fields. */
export const debugPinInput = import.meta.env.VITE_LAOMEDO_DEBUG_PIN_INPUT === "true";
