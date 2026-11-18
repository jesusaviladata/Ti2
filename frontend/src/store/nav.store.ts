import { create } from "zustand";

interface NavState {
  /** Menú lateral abierto como panel en pantallas pequeñas (< lg). */
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
}

export const useNavStore = create<NavState>((set) => ({
  mobileOpen: false,
  setMobileOpen: (mobileOpen) => set({ mobileOpen }),
}));
