/**
 * 익명 사용 패턴 수집 opt-out 토글.
 *
 * 사용자가 체크 해제 시 localStorage 의 OPT_OUT 플래그를 세팅하여
 * 모든 API 요청에서 X-Device-Id 헤더가 빠지고, 서버는 device_id 없는
 * 요청을 자동으로 no-op 처리한다.
 */

import { useState } from 'react';
import { isTrackingEnabled, setTrackingEnabled } from '../lib/device';

interface Props {
  className?: string;
}

export default function TrackingToggle({ className = '' }: Props) {
  const [enabled, setEnabled] = useState<boolean>(isTrackingEnabled());

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.checked;
    setTrackingEnabled(next);
    setEnabled(next);
  };

  return (
    <label className={`flex items-center gap-2 text-xs text-gray-500 ${className}`}>
      <input
        type="checkbox"
        checked={enabled}
        onChange={handleChange}
        className="w-3.5 h-3.5 accent-blue-500"
      />
      <span>익명 사용 패턴 수집 허용 (서비스 개선용)</span>
    </label>
  );
}
