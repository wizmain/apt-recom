import { useState, useEffect, useMemo } from 'react';

interface WeightDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  defaultWeights: Record<string, Record<string, number>>;  // { cost: { _price: 0.3, subway: 0.15 }, ... }
  selectedNudges: string[];
  onApply: (weights: Record<string, number>) => void;
}

const FACILITY_LABELS: Record<string, string> = {
  subway: '지하철역',
  bus: '버스정류장',
  bus_stop: '버스정류장',
  school: '학교',
  kindergarten: '유치원',
  hospital: '병원',
  park: '공원',
  mart: '대형마트',
  convenience_store: '편의점',
  library: '도서관',
  pharmacy: '약국',
  pet_facility: '반려동물시설',
  animal_hospital: '동물병원',
  police: '경찰서',
  fire_station: '소방서',
  cctv: 'CCTV',
  _price: '가격 경쟁력',
  _jeonse: '전세가율',
  _safety: '안전점수',
  _crime: '범죄안전',
};

const NUDGE_LABELS: Record<string, string> = {
  cost: '가성비',
  pet: '반려동물',
  commute: '출퇴근',
  newlywed: '신혼육아',
  education: '학군',
  senior: '시니어',
  investment: '투자',
  nature: '자연친화',
  safety: '안전',
};

export default function WeightDrawer({
  isOpen,
  onClose,
  defaultWeights,
  selectedNudges,
  onApply,
}: WeightDrawerProps) {
  // Merge selected nudges' weights into flat map
  const mergedDefaults = useMemo(() => {
    const merged: Record<string, number> = {};
    for (const nid of selectedNudges) {
      const ws = defaultWeights[nid];
      if (!ws) continue;
      for (const [k, v] of Object.entries(ws)) {
        // Use max if same key in multiple nudges
        merged[k] = Math.max(merged[k] ?? 0, v);
      }
    }
    return merged;
  }, [defaultWeights, selectedNudges]);

  const [weights, setWeights] = useState<Record<string, number>>(mergedDefaults);

  // Sync weights when mergedDefaults changes (nudge selection change)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional sync from prop-derived memo
    setWeights({ ...mergedDefaults });
  }, [mergedDefaults]);

  const handleSliderChange = (key: string, value: number) => {
    setWeights((prev) => ({ ...prev, [key]: value * 0.01 }));
  };

  const handleReset = () => {
    setWeights({ ...mergedDefaults });
  };

  const handleApply = () => {
    onApply(weights);
    onClose();
  };

  const totalWeight = Object.values(weights).reduce((s, v) => s + v, 0);
  const entries = Object.entries(weights);

  return (
    <>
      {/* Overlay */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/20 z-20" onClick={onClose} />
      )}

      {/* Drop-down panel */}
      <div
        className="fixed left-0 right-0 z-30 transition-all duration-300 ease-in-out overflow-hidden"
        style={{ top: 56, maxHeight: isOpen ? 420 : 0, opacity: isOpen ? 1 : 0 }}
      >
        <div className="bg-white border-b border-gray-200 shadow-lg">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-gray-800">세부 가중치 설정</h2>
              {selectedNudges.length > 0 && (
                <div className="flex gap-1">
                  {selectedNudges.map(nid => (
                    <span key={nid} className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded font-medium">
                      {NUDGE_LABELS[nid] || nid}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg cursor-pointer leading-none">✕</button>
          </div>

          {/* Sliders */}
          <div className="px-4 py-3 max-h-[280px] overflow-y-auto">
            {entries.length > 0 ? (
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                {entries.map(([key, value]) => {
                  const pct = totalWeight > 0 ? ((value / totalWeight) * 100).toFixed(0) : '0';
                  const sliderVal = Math.round(value * 100);
                  return (
                    <div key={key}>
                      <div className="flex justify-between items-center mb-1">
                        <label className="text-xs text-gray-600">{FACILITY_LABELS[key] || key}</label>
                        <span className="text-[11px] text-blue-600 font-semibold">{pct}%</span>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={sliderVal}
                        onChange={(e) => handleSliderChange(key, Number(e.target.value))}
                        className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                      />
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-6">
                라이프 항목을 선택하면 가중치가 표시됩니다.
              </p>
            )}
          </div>

          {/* Footer */}
          <div className="flex gap-2 px-4 py-2.5 border-t border-gray-100">
            <button onClick={handleReset}
              className="flex-1 py-1.5 px-3 rounded-lg border border-gray-300 text-gray-600 text-xs font-medium hover:bg-gray-50 transition-colors cursor-pointer">
              초기화
            </button>
            <button onClick={handleApply}
              className="flex-1 py-1.5 px-3 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 transition-colors cursor-pointer">
              적용
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
