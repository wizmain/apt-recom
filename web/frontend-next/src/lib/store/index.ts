import { create } from "zustand";
import { devtools } from "zustand/middleware";
import { createSearchSlice, type SearchSlice } from "./searchSlice";
import { createNudgeSlice, type NudgeSlice } from "./nudgeSlice";
import { createChatSlice, type ChatSlice } from "./chatSlice";
import { createMapSlice, type MapSlice } from "./mapSlice";

export type AppStore = SearchSlice & NudgeSlice & ChatSlice & MapSlice;

export const useAppStore = create<AppStore>()(
  devtools(
    (...a) => ({
      ...createSearchSlice(...a),
      ...createNudgeSlice(...a),
      ...createChatSlice(...a),
      ...createMapSlice(...a),
    }),
    {
      name: "apt-recom",
      enabled: process.env.NODE_ENV !== "production",
    },
  ),
);
