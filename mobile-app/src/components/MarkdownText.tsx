import { View, Text, StyleSheet, Platform } from 'react-native';

interface MarkdownTextProps {
  children: string;
}

/**
 * 경량 마크다운 렌더러 — 외부 의존성 없이 RN Text 기반으로 렌더링.
 * 지원: **bold**, *italic*, `code`, ### 제목, - 리스트, > 인용, --- 구분선
 */
export default function MarkdownText({ children }: MarkdownTextProps) {
  const lines = children.split('\n');
  const elements: React.ReactNode[] = [];
  let listBuffer: string[] = [];
  let quoteBuffer: string[] = [];

  const flushList = () => {
    if (listBuffer.length === 0) return;
    elements.push(
      <View key={`list-${elements.length}`} style={ms.listWrap}>
        {listBuffer.map((item, i) => (
          <View key={i} style={ms.listItem}>
            <Text style={ms.bullet}>•</Text>
            <Text style={ms.listText}>{renderInline(item)}</Text>
          </View>
        ))}
      </View>
    );
    listBuffer = [];
  };

  const flushQuote = () => {
    if (quoteBuffer.length === 0) return;
    elements.push(
      <View key={`quote-${elements.length}`} style={ms.quoteWrap}>
        <Text style={ms.quoteText}>{renderInline(quoteBuffer.join('\n'))}</Text>
      </View>
    );
    quoteBuffer = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // 빈 줄
    if (trimmed === '') {
      flushList();
      flushQuote();
      continue;
    }

    // 구분선
    if (/^[-*_]{3,}$/.test(trimmed)) {
      flushList();
      flushQuote();
      elements.push(<View key={`hr-${i}`} style={ms.hr} />);
      continue;
    }

    // 인용문
    if (trimmed.startsWith('> ')) {
      flushList();
      quoteBuffer.push(trimmed.slice(2));
      continue;
    } else {
      flushQuote();
    }

    // 리스트
    if (/^[-*+]\s/.test(trimmed)) {
      flushQuote();
      listBuffer.push(trimmed.replace(/^[-*+]\s/, ''));
      continue;
    }
    // 숫자 리스트
    if (/^\d+[.)]\s/.test(trimmed)) {
      flushQuote();
      const num = trimmed.match(/^(\d+)[.)]\s/)?.[1] || '';
      const content = trimmed.replace(/^\d+[.)]\s/, '');
      if (listBuffer.length === 0) {
        // 숫자 리스트 시작
      }
      elements.push(
        <View key={`ol-${i}`} style={ms.listItem}>
          <Text style={ms.olNum}>{num}.</Text>
          <Text style={ms.listText}>{renderInline(content)}</Text>
        </View>
      );
      continue;
    } else {
      flushList();
    }

    // 제목
    const headMatch = trimmed.match(/^(#{1,3})\s+(.+)/);
    if (headMatch) {
      flushList();
      flushQuote();
      const level = headMatch[1].length;
      const text = headMatch[2];
      const headStyle = level === 1 ? ms.h1 : level === 2 ? ms.h2 : ms.h3;
      elements.push(<Text key={`h-${i}`} style={headStyle}>{renderInline(text)}</Text>);
      continue;
    }

    // 일반 텍스트
    elements.push(
      <Text key={`p-${i}`} style={ms.para}>{renderInline(trimmed)}</Text>
    );
  }

  flushList();
  flushQuote();

  return <View>{elements}</View>;
}

/** 인라인 마크다운 처리: **bold**, *italic*, `code` */
function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  // 정규식으로 **bold**, *italic*, `code` 파싱
  const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let lastIndex = 0;
  let match;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    // 매치 전 텍스트
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    if (match[2]) {
      // **bold**
      parts.push(<Text key={key++} style={ms.bold}>{match[2]}</Text>);
    } else if (match[3]) {
      // *italic*
      parts.push(<Text key={key++} style={ms.italic}>{match[3]}</Text>);
    } else if (match[4]) {
      // `code`
      parts.push(<Text key={key++} style={ms.inlineCode}>{match[4]}</Text>);
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length === 1 && typeof parts[0] === 'string' ? parts[0] : parts;
}

const ms = StyleSheet.create({
  h1: { fontSize: 17, fontWeight: '800', color: '#111827', marginTop: 8, marginBottom: 4 },
  h2: { fontSize: 15, fontWeight: '700', color: '#111827', marginTop: 6, marginBottom: 3 },
  h3: { fontSize: 14, fontWeight: '700', color: '#374151', marginTop: 4, marginBottom: 2 },
  para: { fontSize: 14, lineHeight: 21, color: '#111827', marginBottom: 4 },
  bold: { fontWeight: '700', color: '#111827' },
  italic: { fontStyle: 'italic' },
  inlineCode: {
    backgroundColor: '#EFF6FF', color: '#1E40AF', fontSize: 13,
    paddingHorizontal: 3, borderRadius: 3,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  listWrap: { marginVertical: 4 },
  listItem: { flexDirection: 'row', marginBottom: 3, paddingLeft: 4 },
  bullet: { color: '#2563EB', fontSize: 14, marginRight: 6, marginTop: 1, fontWeight: '600' },
  olNum: { color: '#2563EB', fontSize: 13, fontWeight: '600', marginRight: 6, marginTop: 1, width: 18 },
  listText: { flex: 1, fontSize: 14, lineHeight: 21, color: '#111827' },
  quoteWrap: {
    borderLeftWidth: 3, borderLeftColor: '#2563EB',
    backgroundColor: '#EFF6FF', borderRadius: 4,
    paddingHorizontal: 10, paddingVertical: 6, marginVertical: 4,
  },
  quoteText: { fontSize: 13, lineHeight: 20, color: '#374151', fontStyle: 'italic' },
  hr: { height: 1, backgroundColor: '#E5E7EB', marginVertical: 8 },
});
