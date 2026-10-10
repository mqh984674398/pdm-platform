import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { parse } from '@vue/compiler-sfc'
import { describe, expect, it } from 'vitest'
import en from '@/i18n/locales/en-US'
import zh from '@/i18n/locales/zh-CN'
import { NAV, NAV_GROUPS } from '@/router/nav'

type Tree = { [k: string]: string | Tree }

function keys(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === 'string' ? [prefix + k] : keys(v, `${prefix}${k}.`),
  )
}

function vueFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f)
    return statSync(p).isDirectory() ? vueFiles(p) : p.endsWith('.vue') ? [p] : []
  })
}

interface Node {
  type: number
  content?: string
  children?: Node[]
}

function rawText(node: Node): string[] {
  // type 2 = plain text node in the Vue template AST
  const own =
    node.type === 2 && /[A-Za-z一-鿿]/.test(node.content ?? '') ? [node.content!.trim()] : []
  return [...own, ...(node.children ?? []).flatMap(rawText)]
}

describe('i18n', () => {
  it('zh-CN and en-US define exactly the same keys', () => {
    expect(keys(en as unknown as Tree).sort()).toEqual(keys(zh as unknown as Tree).sort())
  })

  it('has labels for every navigation entry and group', () => {
    for (const item of NAV) {
      expect(zh.nav[item.name as keyof typeof zh.nav]).toBeTruthy()
      expect(zh.placeholder.purpose[item.name as keyof typeof zh.placeholder.purpose]).toBeTruthy()
    }
    for (const g of NAV_GROUPS) expect(zh.nav[g]).toBeTruthy()
  })

  it('templates contain no hard-coded user-facing text', () => {
    // Language names are intentionally shown in their own language.
    const allowed = new Set(['中文', 'EN'])
    const offenders = vueFiles(join(__dirname, '../../src')).flatMap((f) => {
      const { descriptor } = parse(readFileSync(f, 'utf-8'))
      const ast = descriptor.template?.ast as unknown as Node | undefined
      return ast
        ? rawText(ast)
            .filter((t) => !allowed.has(t))
            .map((t) => `${f}: ${t}`)
        : []
    })
    expect(offenders).toEqual([])
  })
})
