import { deflateSync } from "node:zlib";

// Valid 2 x 3 red PNG, built only from SYNTHETIC test data. Each chunk carries
// its CRC so the real extractor can distinguish metadata absence from damage.
export function syntheticImage(withMetadata = true) {
  function chunk(type, data) {
    const content = Buffer.concat([Buffer.from(type), data]);
    let crc = 0xffffffff;
    for (const byte of content) {
      crc ^= byte;
      for (let i = 0; i < 8; i++)
        crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    const length = Buffer.alloc(4),
      checksum = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    checksum.writeUInt32BE((crc ^ 0xffffffff) >>> 0);
    return Buffer.concat([length, content, checksum]);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(2, 0);
  header.writeUInt32BE(3, 4);
  header[8] = 8;
  header[9] = 2;
  const xmp = `<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" xmlns:exif="http://ns.adobe.com/exif/1.0/" xmlns:tiff="http://ns.adobe.com/tiff/1.0/" exif:DateTimeOriginal="2020-01-02T03:04:05+05:30" exif:GPSLatitude="0,0.000N" exif:GPSLongitude="0,0.000E" tiff:Make="SYNTHETIC camera" /></rdf:RDF></x:xmpmeta>`;
  return Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    chunk("IHDR", header),
    ...(withMetadata
      ? [
          chunk("tEXt", Buffer.from("Description\0SYNTHETIC metadata fixture")),
          chunk("iTXt", Buffer.from(`XML:com.adobe.xmp\0\0\0\0\0${xmp}`)),
        ]
      : []),
    chunk(
      "IDAT",
      deflateSync(
        Buffer.from([
          0, 255, 0, 0, 255, 0, 0, 0, 255, 0, 0, 255, 0, 0, 0, 255, 0, 0, 255,
          0, 0,
        ]),
      ),
    ),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}
