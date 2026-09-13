#include "Rom.hpp"
#include <fstream>
#include <iterator>
std::unique_ptr<Rom> Rom::globalInstance;
Rom Rom::LoadFromFile(const std::filesystem::path &p) { std::ifstream f(p,std::ios::binary); if(!f) throw Xcept("Cannot open ROM"); std::vector<uint8_t> b((std::istreambuf_iterator<char>(f)),{}); return LoadFromBufferCopy(b); }
Rom Rom::LoadFromBufferCopy(std::span<uint8_t> b) { Rom r; r.romContainer.assign(b.begin(),b.end());r.romData=r.romContainer;r.Verify();return r; }
Rom Rom::LoadFromBufferRef(std::span<uint8_t> b) { Rom r;r.romData=b;r.Verify();return r; }
void Rom::CreateInstance(const std::filesystem::path&p){globalInstance=std::make_unique<Rom>(LoadFromFile(p));}
std::string Rom::ReadString(size_t pos,size_t lim) const {std::string s;for(size_t i=0;i<lim&&ReadU8(pos+i);i++)s+=char(ReadU8(pos+i));return s;}
std::string Rom::GetROMCode() const {return ReadString(0xAC,4);}
bool Rom::IsGsf() const {return false;}
void Rom::Verify(){ if(romData.size()>AGB_ROM_SIZE || romData.size()<0x200)throw Xcept("Illegal ROM size");int c=0;for(size_t i=0xA0;i<0xBD;i++)c-=ReadU8(i);c=(c-0x19)&255;if(c!=ReadU8(0xBD))throw Xcept("Bad ROM header checksum"); }
