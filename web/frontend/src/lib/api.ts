/**
 * 공용 axios 인스턴스.
 * 모든 요청에 X-Device-Id 헤더를 자동으로 주입한다.
 * opt-out 된 사용자는 device_id 가 null 이라 헤더 미추가 → 서버가 자동 no-op.
 *
 * SSE 스트리밍(fetch 기반)은 interceptor가 적용되지 않으므로 호출 지점에서
 * getDeviceId()를 직접 읽어 헤더에 넣어야 한다.
 */

import axios from 'axios'
import { API_BASE } from '../config'
import { getDeviceId } from './device'

export const api = axios.create({ baseURL: API_BASE })
export const isCancel = axios.isCancel

api.interceptors.request.use((config) => {
  const id = getDeviceId()
  if (id) {
    config.headers = config.headers ?? {}
    config.headers['X-Device-Id'] = id
  }
  return config
})
