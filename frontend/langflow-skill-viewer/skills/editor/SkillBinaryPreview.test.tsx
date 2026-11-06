import { fireEvent, render, screen } from "@testing-library/react";
import { fromByteArray } from "base64-js";
import SkillBinaryPreview from "./SkillBinaryPreview";

const binary = (bytes: number[], path = "asset.bin") => ({ path, kind: "binary" as const, text: null, bytes: bytes.length, file_hash: "internal-only", contentBase64: fromByteArray(new Uint8Array(bytes)) });
test("inert raster bytes render as an image even after an upload; decode failure exposes exact bytes", () => {
  render(<SkillBinaryPreview file={binary([137,80,78,71,13,10,26,10,0], 'asset.png')} />);
  const image = screen.getByRole('img', { name: 'Preview of asset.png' });
  expect(screen.queryByText(/internal-only|bytes ·/)).toBeNull();
  expect(image).toHaveClass('absolute', 'h-full', 'w-full', 'object-contain');
  expect(image).toHaveAttribute('src', expect.stringMatching(/^data:image\/png;base64,/));
  fireEvent.error(image);
  expect(screen.getByLabelText('Hex bytes: asset.png')).toHaveTextContent('89 50 4e 47 0d 0a 1a 0a 00');
});
test("unknown/PDF/SVG bytes never enter an executable document or image; large views are paged", () => {
  const bytes = [0,60,115,118,103,62,...Array(5000).fill(65)];
  const { container } = render(<SkillBinaryPreview file={binary(bytes, 'asset.svg')} />);
  expect(screen.queryByText(/internal-only|bytes ·/)).toBeNull();
  expect(container.querySelector('img, iframe, object, embed, script')).toBeNull();
  expect(screen.getByLabelText('Hex bytes: asset.svg')).toHaveTextContent('00000000');
  fireEvent.click(screen.getByRole('button', { name: 'Show more bytes' }));
  expect(screen.queryByRole('button', { name: 'Show more bytes' })).toBeNull();
});
