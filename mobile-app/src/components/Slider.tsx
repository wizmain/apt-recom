import { useRef, useCallback } from 'react';
import { View, StyleSheet, GestureResponderEvent } from 'react-native';

interface SliderProps {
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}

export default function Slider({ value, min, max, onChange }: SliderProps) {
  const containerRef = useRef<View>(null);
  const layoutRef = useRef({ x: 0, width: 0 });

  const ratio = max > min ? (value - min) / (max - min) : 0;

  const handleTouch = useCallback((pageX: number) => {
    const { x, width } = layoutRef.current;
    if (width <= 0) return;
    const localX = Math.max(0, Math.min(pageX - x, width));
    const newVal = Math.round(min + (localX / width) * (max - min));
    onChange(newVal);
  }, [min, max, onChange]);

  const onStart = useCallback((e: GestureResponderEvent) => {
    // 터치 시작 시 컨테이너 절대 좌표 측정
    containerRef.current?.measureInWindow((px, _py, w) => {
      layoutRef.current = { x: px, width: w };
      handleTouch(e.nativeEvent.pageX);
    });
  }, [handleTouch]);

  const onMove = useCallback((e: GestureResponderEvent) => {
    handleTouch(e.nativeEvent.pageX);
  }, [handleTouch]);

  return (
    <View
      ref={containerRef}
      style={s.container}
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderGrant={onStart}
      onResponderMove={onMove}
    >
      <View style={s.track}>
        <View style={[s.fill, { width: `${ratio * 100}%` }]} />
      </View>
      <View style={[s.thumb, { left: `${ratio * 100}%` }]} />
    </View>
  );
}

const s = StyleSheet.create({
  container: { height: 36, justifyContent: 'center' },
  track: { height: 4, backgroundColor: '#E5E7EB', borderRadius: 2, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: '#2563EB', borderRadius: 2 },
  thumb: {
    position: 'absolute',
    width: 22, height: 22,
    borderRadius: 11,
    backgroundColor: '#2563EB',
    borderWidth: 2.5,
    borderColor: '#FFF',
    marginLeft: -11,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 3,
    elevation: 3,
  },
});
