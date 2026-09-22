import { useState } from 'react'
import { Icon } from '../Icon'
import { Range as RangeControl, Sheet } from '../ui'
import { useSettings } from '../../state/settings'
import { AMBIENCES } from '../../lib/ambient'
import type { VoiceOption } from '../../lib/tts'

const SPEEDS = [0.75, 0.9, 1, 1.15, 1.3, 1.5, 1.75, 2]

interface ListenBarProps {
  playing: boolean
  sentenceText: string
  chapterTitle: string
  voices: { featured: VoiceOption[]; all: VoiceOption[] }
  onToggle: () => void
  onPrevious: () => void
  onNext: () => void
  onClose: () => void
}

export function ListenBar({
  playing,
  sentenceText,
  chapterTitle,
  voices,
  onToggle,
  onPrevious,
  onNext,
  onClose,
}: ListenBarProps) {
  const { settings, set } = useSettings()
  const [showAmbience, setShowAmbience] = useState(false)
  const [showVoices, setShowVoices] = useState(false)

  const activeVoice =
    voices.all.find((voice) => voice.uri === settings.voiceURI) ?? voices.featured[0]
  const ambience = AMBIENCES.find((item) => item.id === settings.ambience) ?? AMBIENCES[0]

  return (
    <div className="listen" role="region" aria-label="Listen mode">
      <div className="listen__main">
        <button
          type="button"
          className="listen__play"
          onClick={onToggle}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          <Icon name={playing ? 'pause' : 'play'} size={21} fill={!playing} strokeWidth={playing ? 1.8 : 1} />
        </button>

        <button type="button" className="icon-btn" onClick={onPrevious} aria-label="Previous sentence">
          <Icon name="skipBack" size={18} />
        </button>
        <button type="button" className="icon-btn" onClick={onNext} aria-label="Next sentence">
          <Icon name="skipForward" size={18} />
        </button>

        <div className="listen__now">
          <div className="listen__label">{playing ? 'Listening' : 'Paused'}</div>
          <div className="listen__text">{sentenceText || chapterTitle}</div>
        </div>

        <button type="button" className="icon-btn" onClick={onClose} aria-label="Leave listen mode">
          <Icon name="x" size={18} />
        </button>
      </div>

      <div className="listen__row">
        <label className="listen__chip" style={{ paddingRight: 4 }}>
          <Icon name="gauge" size={15} />
          <select
            className="listen__select"
            style={{ border: 'none', background: 'transparent', height: 22, paddingLeft: 2 }}
            value={settings.rate}
            onChange={(event) => set('rate', Number(event.target.value))}
            aria-label="Speed"
          >
            {SPEEDS.map((speed) => (
              <option key={speed} value={speed}>
                {speed}×
              </option>
            ))}
          </select>
        </label>

        <button type="button" className="listen__chip" onClick={() => setShowVoices(true)}>
          <Icon name="user" size={15} />
          {activeVoice ? activeVoice.label.split(' · ').pop() : 'Voice'}
        </button>

        <button
          type="button"
          className={`listen__chip${settings.ambience !== 'none' ? ' is-on' : ''}`}
          onClick={() => setShowAmbience(true)}
        >
          <Icon name="wind" size={15} />
          {ambience.name}
        </button>
      </div>

      <Sheet open={showVoices} onClose={() => setShowVoices(false)} title="Voice">
        <div className="sheet__body">
          {voices.featured.length > 0 && (
            <div className="tune__group">
              <span className="tune__label">Picked for you</span>
              <div className="font-row">
                {voices.featured.map((voice) => (
                  <button
                    key={voice.uri}
                    type="button"
                    className="font-option"
                    aria-pressed={settings.voiceURI === voice.uri}
                    onClick={() => set('voiceURI', voice.uri)}
                  >
                    <span className="font-option__name">{voice.label}</span>
                    <span className="font-option__note">
                      {voice.lang}
                      {voice.local ? ' · offline' : ''}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {voices.all.length > voices.featured.length && (
            <div className="field">
              <label className="field__label" htmlFor="all-voices">
                Every voice on this device ({voices.all.length})
              </label>
              <select
                id="all-voices"
                className="input"
                value={settings.voiceURI ?? ''}
                onChange={(event) => set('voiceURI', event.target.value || null)}
              >
                <option value="">System default</option>
                {voices.all.map((voice) => (
                  <option key={voice.uri} value={voice.uri}>
                    {voice.name} ({voice.lang})
                  </option>
                ))}
              </select>
            </div>
          )}

          <RangeControl
            label="Pitch"
            value={settings.pitch}
            min={0.6}
            max={1.4}
            step={0.05}
            onChange={(value) => set('pitch', value)}
            format={(value) => value.toFixed(2)}
          />
          <RangeControl
            label="Voice volume"
            value={settings.ttsVolume}
            min={0}
            max={1}
            step={0.05}
            onChange={(value) => set('ttsVolume', value)}
            format={(value) => `${Math.round(value * 100)}%`}
          />

          {!voices.all.length && (
            <p className="panel__empty" style={{ padding: '12px 0' }}>
              No speech voices were found in this browser. On desktop Linux install a speech engine;
              on other systems check your accessibility settings.
            </p>
          )}
        </div>
      </Sheet>

      <Sheet open={showAmbience} onClose={() => setShowAmbience(false)} title="Ambient sound">
        <div className="sheet__body">
          <div className="font-row">
            {AMBIENCES.map((option) => (
              <button
                key={option.id}
                type="button"
                className="font-option"
                aria-pressed={settings.ambience === option.id}
                onClick={() => set('ambience', option.id)}
              >
                <Icon name={option.id === 'none' ? 'volumeOff' : 'wind'} size={16} />
                <span className="font-option__name">{option.name}</span>
                <span className="font-option__note">{option.hint}</span>
              </button>
            ))}
          </div>
          <RangeControl
            label="Ambient volume"
            value={settings.ambienceVolume}
            min={0}
            max={0.8}
            step={0.02}
            onChange={(value) => set('ambienceVolume', value)}
            format={(value) => `${Math.round((value / 0.8) * 100)}%`}
          />
          <p className="row__hint" style={{ margin: 0 }}>
            These are generated live in your browser, so they never repeat and work offline.
          </p>
        </div>
      </Sheet>
    </div>
  )
}
