"use client";

import { useContext } from "react";
import Link from "next/link";
import { logEvent } from "@/lib/logEvent";
import { EmbedContext } from "./EmbedContext";

/** 단지 상세 링크 + content_apartment_click 이벤트. pnu 없거나 임베드면 텍스트만. */
export function ApartmentLink({
  slug,
  pnu,
  rank,
  name,
}: {
  slug: string;
  pnu: string | null;
  rank: number;
  name: string;
}) {
  const embed = useContext(EmbedContext);
  if (embed || !pnu)
    return <span className="font-semibold text-gray-900">{name}</span>;
  return (
    <Link
      href={`/apartment/${pnu}`}
      className="font-semibold text-blue-700 hover:underline"
      onClick={() => logEvent("content_apartment_click", { slug, pnu, rank })}
    >
      {name}
    </Link>
  );
}
