// Document-space bounding boxes for items and selections.

import type { Item, Project } from '../types'
import { cachedPathBBox } from './pathBBox'
import { rectCorners, unionPts, unionRects, type Rect } from './matrix'

/** Bbox of one item in document (mm) space; null if the path is empty. */
export function itemBox(item: Item): Rect | null {
  const local = cachedPathBBox(item.d)
  if (!local) return null
  return unionPts(rectCorners(local, item.transform as never))
}

/** Union bbox of the selection in doc space; null when the selection is empty. */
export function selectionBox(doc: Project, selection: string[]): Rect | null {
  if (selection.length === 0) return null
  const sel = new Set(selection)
  const boxes: Rect[] = []
  for (const layer of doc.layers) {
    for (const it of layer.items) {
      if (!sel.has(it.id)) continue
      const b = itemBox(it)
      if (b) boxes.push(b)
    }
  }
  return unionRects(boxes)
}