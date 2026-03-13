/**
 * usePhotoLibrary -- expo-media-library wrapper for Elora
 *
 * Lets Elora browse the user's camera roll:
 *   - requestPermissions()
 *   - getRecentPhotos(limit) → asset URIs
 *   - searchPhotos(query)    → assets matching date / album / type
 *
 * The URIs returned can be displayed directly in <Image /> or sent to the
 * backend as base64 for Gemini Vision analysis (see sendImage in useElora).
 */

import { useState, useCallback } from "react";
import * as MediaLibrary from "expo-media-library";

export interface PhotoAsset {
  id: string;
  uri: string;
  filename: string;
  creationTime: number; // unix ms
  mediaType: string;
  width: number;
  height: number;
  albumId?: string;
}

export interface UsePhotoLibraryReturn {
  hasPermission: boolean | null;
  requestPermissions: () => Promise<boolean>;
  getRecentPhotos: (limit?: number) => Promise<PhotoAsset[]>;
  searchPhotos: (query: PhotoSearchQuery) => Promise<PhotoAsset[]>;
  getPhotoBase64: (uri: string) => Promise<string | null>;
}

export interface PhotoSearchQuery {
  /** Free-text description — matched against filename / album name */
  text?: string;
  /** Album name to search within */
  album?: string;
  /** Only return photos after this date (unix ms) */
  after?: number;
  /** Only return photos before this date (unix ms) */
  before?: number;
  /** Max results */
  limit?: number;
  mediaType?: "photo" | "video" | "all";
}

export function usePhotoLibrary(): UsePhotoLibraryReturn {
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);

  const requestPermissions = useCallback(async (): Promise<boolean> => {
    const { status } = await MediaLibrary.requestPermissionsAsync();
    const granted = status === "granted";
    setHasPermission(granted);
    return granted;
  }, []);

  const getRecentPhotos = useCallback(
    async (limit = 20): Promise<PhotoAsset[]> => {
      // Auto-request if not yet asked
      if (hasPermission === null) {
        const granted = await requestPermissions();
        if (!granted) return [];
      } else if (!hasPermission) {
        return [];
      }

      try {
        const result = await MediaLibrary.getAssetsAsync({
          first: limit,
          mediaType: ["photo"],
          sortBy: [MediaLibrary.SortBy.creationTime],
        });
        return result.assets.map(_toPhotoAsset);
      } catch (e) {
        console.warn("[usePhotoLibrary] getRecentPhotos error:", e);
        return [];
      }
    },
    [hasPermission, requestPermissions]
  );

  const searchPhotos = useCallback(
    async (query: PhotoSearchQuery): Promise<PhotoAsset[]> => {
      if (hasPermission === null) {
        const granted = await requestPermissions();
        if (!granted) return [];
      } else if (!hasPermission) {
        return [];
      }

      try {
        const limit = query.limit ?? 30;
        const mediaType: MediaLibrary.MediaTypeValue[] =
          query.mediaType === "video"
            ? ["video"]
            : query.mediaType === "all"
            ? ["photo", "video"]
            : ["photo"];

        // If an album name is given, find the album first
        let albumId: string | undefined;
        if (query.album) {
          const album = await MediaLibrary.getAlbumAsync(query.album);
          if (album) albumId = album.id;
        }

        const opts: MediaLibrary.AssetsOptions = {
          first: limit,
          mediaType,
          sortBy: [MediaLibrary.SortBy.creationTime],
          ...(albumId ? { album: albumId } : {}),
          ...(query.after !== undefined ? { createdAfter: query.after } : {}),
          ...(query.before !== undefined ? { createdBefore: query.before } : {}),
        };

        const result = await MediaLibrary.getAssetsAsync(opts);
        let assets = result.assets.map(_toPhotoAsset);

        // Client-side text filter on filename
        if (query.text) {
          const q = query.text.toLowerCase();
          assets = assets.filter(
            (a) =>
              a.filename.toLowerCase().includes(q) ||
              (a.albumId ?? "").toLowerCase().includes(q)
          );
        }

        return assets;
      } catch (e) {
        console.warn("[usePhotoLibrary] searchPhotos error:", e);
        return [];
      }
    },
    [hasPermission, requestPermissions]
  );

  /**
   * Read a photo asset as a base64 string (jpeg).
   * Use this to send a photo to Elora's vision for analysis.
   */
  const getPhotoBase64 = useCallback(
    async (uri: string): Promise<string | null> => {
      try {
        const FileSystem = await import("expo-file-system/legacy");
        const base64 = await FileSystem.readAsStringAsync(uri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        return base64;
      } catch (e) {
        console.warn("[usePhotoLibrary] getPhotoBase64 error:", e);
        return null;
      }
    },
    []
  );

  return {
    hasPermission,
    requestPermissions,
    getRecentPhotos,
    searchPhotos,
    getPhotoBase64,
  };
}

function _toPhotoAsset(asset: MediaLibrary.Asset): PhotoAsset {
  return {
    id: asset.id,
    uri: asset.uri,
    filename: asset.filename,
    creationTime: asset.creationTime,
    mediaType: asset.mediaType,
    width: asset.width,
    height: asset.height,
    albumId: asset.albumId,
  };
}
