"use client";

import { useMemo, useSyncExternalStore } from "react";

export type ModelCategory = "llm" | "image";

export const FAVORITE_LLM_MODELS_KEY = "clair_favorite_models";
export const FAVORITE_IMAGE_MODELS_KEY = "clair_favorite_image_models";
export const MODEL_FAVORITES_EVENT = "clair-model-favorites-changed";

export function getFavoritesStorageKey(category: ModelCategory = "llm"): string {
  return category === "image" ? FAVORITE_IMAGE_MODELS_KEY : FAVORITE_LLM_MODELS_KEY;
}

export function readFavoriteModels(category: ModelCategory = "llm"): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(getFavoritesStorageKey(category));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  } catch {
    return [];
  }
}

export function saveFavoriteModels(models: string[], category: ModelCategory = "llm"): boolean {
  if (typeof window === "undefined") return false;
  const unique = Array.from(new Set(models.filter((item): item is string => typeof item === "string" && item.trim().length > 0)));
  const key = getFavoritesStorageKey(category);
  try {
    window.localStorage.setItem(key, JSON.stringify(unique));
  } catch {
    return false;
  }

  try {
    window.dispatchEvent(
      new CustomEvent(MODEL_FAVORITES_EVENT, {
        detail: { category, favorites: unique },
      })
    );
  } catch {
    // CustomEvent dispatch failure is non-fatal
  }
  return true;
}

export function toggleFavoriteModel(modelId: string, category: ModelCategory = "llm"): boolean {
  if (!modelId) return false;
  const current = readFavoriteModels(category);
  const exists = current.includes(modelId);
  const updated = exists ? current.filter((id) => id !== modelId) : [modelId, ...current];
  saveFavoriteModels(updated, category);
  return !exists;
}

export function isModelFavorite(modelId: string, favorites: string[] | Set<string>): boolean {
  if (!modelId) return false;
  if (favorites instanceof Set) return favorites.has(modelId);
  return favorites.includes(modelId);
}

/**
 * Sorts an array of models so that favorite models appear at the top ("en tête"),
 * preserving relative order among favorites and non-favorites.
 */
export function sortModelsWithFavorites<T extends { id: string }>(
  items: T[],
  favorites: string[] | Set<string>,
  currentModelId?: string
): T[] {
  const favSet = favorites instanceof Set ? favorites : new Set(favorites);

  return [...items].sort((a, b) => {
    const aFav = favSet.has(a.id);
    const bFav = favSet.has(b.id);

    // 1. Favorites come first
    if (aFav && !bFav) return -1;
    if (!aFav && bFav) return 1;

    // 2. Active model first within its category (within favorites or non-favorites)
    if (currentModelId) {
      if (a.id === currentModelId) return -1;
      if (b.id === currentModelId) return 1;
    }

    return 0;
  });
}

const cachedRaw: Record<ModelCategory, string | null> = { llm: null, image: null };
const cachedParsed: Record<ModelCategory, string[]> = { llm: [], image: [] };

function getFavoritesSnapshot(category: ModelCategory): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(getFavoritesStorageKey(category));
    if (raw === cachedRaw[category]) {
      return cachedParsed[category];
    }
    cachedRaw[category] = raw;
    if (!raw) {
      cachedParsed[category] = [];
    } else {
      const parsed = JSON.parse(raw);
      cachedParsed[category] = Array.isArray(parsed)
        ? parsed.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
        : [];
    }
    return cachedParsed[category];
  } catch {
    return [];
  }
}

const SERVER_EMPTY_SNAPSHOT: string[] = [];

/**
 * React hook for accessing and toggling favorite models with cross-component synchronization.
 */
export function useModelFavorites(category: ModelCategory = "llm") {
  const favorites = useSyncExternalStore(
    (onStoreChange) => {
      const handleCustom = (e: Event) => {
        const custom = e as CustomEvent<{ category?: ModelCategory }>;
        if (!custom.detail || custom.detail.category === category) {
          onStoreChange();
        }
      };

      const handleStorage = (e: StorageEvent) => {
        if (e.key === getFavoritesStorageKey(category)) {
          onStoreChange();
        }
      };

      window.addEventListener(MODEL_FAVORITES_EVENT, handleCustom);
      window.addEventListener("storage", handleStorage);

      return () => {
        window.removeEventListener(MODEL_FAVORITES_EVENT, handleCustom);
        window.removeEventListener("storage", handleStorage);
      };
    },
    () => getFavoritesSnapshot(category),
    () => SERVER_EMPTY_SNAPSHOT
  );

  const favoritesSet = useMemo(() => new Set(favorites), [favorites]);

  const isFavorite = (modelId: string) => favoritesSet.has(modelId);

  const toggleFavorite = (modelId: string) => {
    return toggleFavoriteModel(modelId, category);
  };

  const setFavorites = (models: string[]) => {
    saveFavoriteModels(models, category);
  };

  return {
    favorites,
    favoritesSet,
    isFavorite,
    toggleFavorite,
    setFavorites,
  };
}
