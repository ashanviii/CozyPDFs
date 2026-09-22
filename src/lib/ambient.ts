/**
 * Ambient sound, synthesized.
 *
 * Every scene is built from noise, filters and a scattering of scheduled
 * one-shots — no audio files. That keeps the app small, works offline, and
 * lets a scene run forever without an audible loop point.
 */
import type { Ambience } from './types'

export const AMBIENCES: { id: Ambience; name: string; hint: string }[] = [
  { id: 'none', name: 'Silence', hint: 'No background sound' },
  { id: 'rain', name: 'Rain', hint: 'Steady rain on a window' },
  { id: 'fireplace', name: 'Fireplace', hint: 'A low fire, crackling' },
  { id: 'cafe', name: 'Café', hint: 'Distant chatter and cups' },
  { id: 'forest', name: 'Forest', hint: 'Wind in leaves, birdsong' },
]

type Scene = {
  nodes: AudioNode[]
  timers: number[]
}

const NOISE_SECONDS = 4

function whiteNoiseBuffer(ctx: AudioContext) {
  const buffer = ctx.createBuffer(1, ctx.sampleRate * NOISE_SECONDS, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  return buffer
}

function brownNoiseBuffer(ctx: AudioContext) {
  const buffer = ctx.createBuffer(1, ctx.sampleRate * NOISE_SECONDS, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  let last = 0
  for (let i = 0; i < data.length; i++) {
    const white = Math.random() * 2 - 1
    last = (last + 0.02 * white) / 1.02
    data[i] = last * 3.2
  }
  return buffer
}

function pinkNoiseBuffer(ctx: AudioContext) {
  // Voss-McCartney, abbreviated — plenty for a wind bed.
  const buffer = ctx.createBuffer(1, ctx.sampleRate * NOISE_SECONDS, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0
  for (let i = 0; i < data.length; i++) {
    const white = Math.random() * 2 - 1
    b0 = 0.99886 * b0 + white * 0.0555179
    b1 = 0.99332 * b1 + white * 0.0750759
    b2 = 0.969 * b2 + white * 0.153852
    b3 = 0.8665 * b3 + white * 0.3104856
    b4 = 0.55 * b4 + white * 0.5329522
    b5 = -0.7616 * b5 - white * 0.016898
    data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11
    b6 = white * 0.115926
  }
  return buffer
}

const rand = (min: number, max: number) => min + Math.random() * (max - min)

export class AmbientPlayer {
  private ctx: AudioContext | null = null
  private master: GainNode | null = null
  private scene: Scene | null = null
  private buffers = new Map<string, AudioBuffer>()
  private current: Ambience = 'none'
  private volume = 0.35
  private running = false

  get active() {
    return this.running && this.current !== 'none'
  }

  get sceneId() {
    return this.current
  }

  private ensureContext() {
    if (!this.ctx) {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return null
      this.ctx = new Ctor()
      this.master = this.ctx.createGain()
      this.master.gain.value = 0
      this.master.connect(this.ctx.destination)
    }
    return this.ctx
  }

  private buffer(kind: 'white' | 'brown' | 'pink') {
    const ctx = this.ensureContext()!
    let buffer = this.buffers.get(kind)
    if (!buffer) {
      buffer = kind === 'white' ? whiteNoiseBuffer(ctx) : kind === 'brown' ? brownNoiseBuffer(ctx) : pinkNoiseBuffer(ctx)
      this.buffers.set(kind, buffer)
    }
    return buffer
  }

  private noiseSource(kind: 'white' | 'brown' | 'pink') {
    const ctx = this.ensureContext()!
    const source = ctx.createBufferSource()
    source.buffer = this.buffer(kind)
    source.loop = true
    source.start()
    return source
  }

  /** Must be called from a user gesture the first time round. */
  async resume() {
    const ctx = this.ensureContext()
    if (!ctx) return false
    if (ctx.state === 'suspended') await ctx.resume()
    return ctx.state === 'running'
  }

  setVolume(volume: number) {
    this.volume = Math.min(1, Math.max(0, volume))
    if (this.master && this.ctx) {
      const target = this.running && this.current !== 'none' ? this.volume : 0
      this.master.gain.cancelScheduledValues(this.ctx.currentTime)
      this.master.gain.setTargetAtTime(target, this.ctx.currentTime, 0.15)
    }
  }

  async play(scene: Ambience) {
    this.current = scene
    if (scene === 'none') {
      this.stop()
      return
    }
    const ok = await this.resume()
    if (!ok) return
    this.teardown()
    this.running = true
    this.scene = this.build(scene)
    this.fadeTo(this.volume, 1.2)
  }

  stop() {
    if (!this.ctx || !this.master) {
      this.running = false
      return
    }
    this.running = false
    this.fadeTo(0, 0.6)
    const scene = this.scene
    this.scene = null
    window.setTimeout(() => this.disposeScene(scene), 900)
  }

  private fadeTo(value: number, seconds: number) {
    if (!this.ctx || !this.master) return
    const now = this.ctx.currentTime
    this.master.gain.cancelScheduledValues(now)
    this.master.gain.setValueAtTime(this.master.gain.value, now)
    this.master.gain.linearRampToValueAtTime(value, now + seconds)
  }

  private teardown() {
    const scene = this.scene
    this.scene = null
    this.disposeScene(scene)
  }

  private disposeScene(scene: Scene | null) {
    if (!scene) return
    for (const timer of scene.timers) clearTimeout(timer)
    for (const node of scene.nodes) {
      try {
        if ('stop' in node && typeof (node as AudioScheduledSourceNode).stop === 'function') {
          ;(node as AudioScheduledSourceNode).stop()
        }
      } catch {
        /* already stopped */
      }
      try {
        node.disconnect()
      } catch {
        /* already disconnected */
      }
    }
  }

  /** Schedules a repeating one-shot at randomised intervals. */
  private every(scene: Scene, minMs: number, maxMs: number, fire: () => void) {
    const tick = () => {
      if (!this.running) return
      fire()
      scene.timers.push(window.setTimeout(tick, rand(minMs, maxMs)))
    }
    scene.timers.push(window.setTimeout(tick, rand(minMs, maxMs)))
  }

  private build(kind: Ambience): Scene {
    const ctx = this.ensureContext()!
    const scene: Scene = { nodes: [], timers: [] }
    const out = this.master!

    const gain = (value: number) => {
      const node = ctx.createGain()
      node.gain.value = value
      scene.nodes.push(node)
      return node
    }

    switch (kind) {
      case 'rain': {
        // Two noise beds: a hiss for the spray, a lowpass body for the downpour.
        const hiss = this.noiseSource('white')
        const hissFilter = ctx.createBiquadFilter()
        hissFilter.type = 'bandpass'
        hissFilter.frequency.value = 2200
        hissFilter.Q.value = 0.45
        const hissGain = gain(0.5)
        hiss.connect(hissFilter).connect(hissGain).connect(out)

        const body = this.noiseSource('brown')
        const bodyFilter = ctx.createBiquadFilter()
        bodyFilter.type = 'lowpass'
        bodyFilter.frequency.value = 780
        const bodyGain = gain(0.38)
        body.connect(bodyFilter).connect(bodyGain).connect(out)

        // A slow gust LFO keeps it from sounding like static.
        const lfo = ctx.createOscillator()
        lfo.frequency.value = 0.045
        const lfoGain = gain(520)
        lfo.connect(lfoGain).connect(hissFilter.frequency)
        lfo.start()

        scene.nodes.push(hiss, hissFilter, body, bodyFilter, lfo)

        // Individual drops hitting the glass.
        this.every(scene, 140, 900, () => {
          const drop = ctx.createOscillator()
          const dropGain = ctx.createGain()
          const t = ctx.currentTime
          drop.type = 'sine'
          drop.frequency.setValueAtTime(rand(700, 1900), t)
          drop.frequency.exponentialRampToValueAtTime(rand(180, 420), t + 0.06)
          dropGain.gain.setValueAtTime(0, t)
          dropGain.gain.linearRampToValueAtTime(rand(0.012, 0.05), t + 0.004)
          dropGain.gain.exponentialRampToValueAtTime(0.0001, t + 0.09)
          drop.connect(dropGain).connect(out)
          drop.start(t)
          drop.stop(t + 0.12)
        })
        break
      }

      case 'fireplace': {
        const roar = this.noiseSource('brown')
        const roarFilter = ctx.createBiquadFilter()
        roarFilter.type = 'lowpass'
        roarFilter.frequency.value = 340
        const roarGain = gain(0.8)
        roar.connect(roarFilter).connect(roarGain).connect(out)

        const air = this.noiseSource('pink')
        const airFilter = ctx.createBiquadFilter()
        airFilter.type = 'bandpass'
        airFilter.frequency.value = 900
        airFilter.Q.value = 0.7
        const airGain = gain(0.16)
        air.connect(airFilter).connect(airGain).connect(out)

        // Flames breathe.
        const lfo = ctx.createOscillator()
        lfo.frequency.value = 0.12
        const lfoGain = gain(0.28)
        lfo.connect(lfoGain).connect(roarGain.gain)
        lfo.start()

        scene.nodes.push(roar, roarFilter, air, airFilter, lfo)

        // Crackles and the occasional pop.
        this.every(scene, 90, 700, () => {
          const t = ctx.currentTime
          const burst = ctx.createBufferSource()
          burst.buffer = this.buffer('white')
          burst.loop = true
          const shaper = ctx.createBiquadFilter()
          shaper.type = 'bandpass'
          shaper.frequency.value = rand(1400, 5200)
          shaper.Q.value = rand(2, 9)
          const env = ctx.createGain()
          const peak = Math.random() < 0.08 ? rand(0.12, 0.26) : rand(0.02, 0.08)
          env.gain.setValueAtTime(0, t)
          env.gain.linearRampToValueAtTime(peak, t + 0.003)
          env.gain.exponentialRampToValueAtTime(0.0001, t + rand(0.04, 0.16))
          burst.connect(shaper).connect(env).connect(out)
          burst.start(t)
          burst.stop(t + 0.2)
        })
        break
      }

      case 'cafe': {
        const room = this.noiseSource('brown')
        const roomFilter = ctx.createBiquadFilter()
        roomFilter.type = 'lowpass'
        roomFilter.frequency.value = 480
        const roomGain = gain(0.5)
        room.connect(roomFilter).connect(roomGain).connect(out)

        // Babble: mid-band noise wobbled at speech-ish rates.
        const babble = this.noiseSource('pink')
        const babbleFilter = ctx.createBiquadFilter()
        babbleFilter.type = 'bandpass'
        babbleFilter.frequency.value = 1100
        babbleFilter.Q.value = 1.6
        const babbleGain = gain(0.12)
        babble.connect(babbleFilter).connect(babbleGain).connect(out)

        const wobble = ctx.createOscillator()
        wobble.frequency.value = 2.7
        const wobbleGain = gain(0.07)
        wobble.connect(wobbleGain).connect(babbleGain.gain)
        wobble.start()

        const sway = ctx.createOscillator()
        sway.frequency.value = 0.09
        const swayGain = gain(320)
        sway.connect(swayGain).connect(babbleFilter.frequency)
        sway.start()

        scene.nodes.push(room, roomFilter, babble, babbleFilter, wobble, sway)

        // Cups, saucers, a spoon.
        this.every(scene, 2600, 11000, () => {
          const t = ctx.currentTime
          const partials = Math.random() < 0.5 ? [2300, 3700] : [1650, 2900, 4300]
          partials.forEach((frequency, index) => {
            const osc = ctx.createOscillator()
            const env = ctx.createGain()
            osc.type = 'sine'
            osc.frequency.value = frequency * rand(0.96, 1.04)
            const peak = rand(0.015, 0.04) / (index + 1)
            env.gain.setValueAtTime(0, t)
            env.gain.linearRampToValueAtTime(peak, t + 0.002)
            env.gain.exponentialRampToValueAtTime(0.0001, t + rand(0.18, 0.5))
            osc.connect(env).connect(out)
            osc.start(t)
            osc.stop(t + 0.6)
          })
        })
        break
      }

      case 'forest': {
        const wind = this.noiseSource('pink')
        const windFilter = ctx.createBiquadFilter()
        windFilter.type = 'bandpass'
        windFilter.frequency.value = 620
        windFilter.Q.value = 0.55
        const windGain = gain(0.55)
        wind.connect(windFilter).connect(windGain).connect(out)

        const leaves = this.noiseSource('white')
        const leafFilter = ctx.createBiquadFilter()
        leafFilter.type = 'highpass'
        leafFilter.frequency.value = 3400
        const leafGain = gain(0.07)
        leaves.connect(leafFilter).connect(leafGain).connect(out)

        const gust = ctx.createOscillator()
        gust.frequency.value = 0.07
        const gustGain = gain(0.34)
        gust.connect(gustGain).connect(windGain.gain)
        gust.start()

        const rustle = ctx.createOscillator()
        rustle.frequency.value = 0.11
        const rustleGain = gain(0.05)
        rustle.connect(rustleGain).connect(leafGain.gain)
        rustle.start()

        scene.nodes.push(wind, windFilter, leaves, leafFilter, gust, rustle)

        // Birdsong: a few swept sine chirps in a phrase.
        this.every(scene, 3500, 13000, () => {
          const base = rand(1900, 3600)
          const notes = Math.floor(rand(2, 5))
          const spacing = rand(0.09, 0.2)
          for (let n = 0; n < notes; n++) {
            const t = ctx.currentTime + n * spacing
            const osc = ctx.createOscillator()
            const env = ctx.createGain()
            osc.type = 'sine'
            const from = base * rand(0.9, 1.1)
            osc.frequency.setValueAtTime(from, t)
            osc.frequency.exponentialRampToValueAtTime(from * rand(1.12, 1.5), t + 0.05)
            osc.frequency.exponentialRampToValueAtTime(from * rand(0.7, 0.95), t + 0.11)
            env.gain.setValueAtTime(0, t)
            env.gain.linearRampToValueAtTime(rand(0.02, 0.055), t + 0.012)
            env.gain.exponentialRampToValueAtTime(0.0001, t + 0.13)
            osc.connect(env).connect(out)
            osc.start(t)
            osc.stop(t + 0.18)
          }
        })
        break
      }

      default:
        break
    }

    return scene
  }

  dispose() {
    this.teardown()
    void this.ctx?.close()
    this.ctx = null
    this.master = null
    this.buffers.clear()
  }
}

export const ambient = new AmbientPlayer()
