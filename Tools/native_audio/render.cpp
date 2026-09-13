// NXT offline render adapter. Linked only to the bundled LGPL agbplay core.
#include "MP2KContext.hpp"
#include "MP2KScanner.hpp"
#include "Debug.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <set>
static void log_cb(const std::string&s,void*){std::cerr<<s<<'\n';if(s.find("Error:")!=std::string::npos)throw std::runtime_error(s);}
static void write32(std::ostream& f,uint32_t n){for(int i=0;i<4;i++)f.put(char(n>>(i*8)));}
static void write16(std::ostream& f,uint16_t n){for(int i=0;i<2;i++)f.put(char(n>>(i*8)));}
static void wave(const std::string&p,const std::vector<sample>&samples,float gain,uint32_t rate){
 std::ofstream f(p,std::ios::binary);if(!f)throw Xcept("Cannot write WAV");
 f.write("RIFF",4);write32(f,36+uint32_t(samples.size()*4));f.write("WAVEfmt ",8);write32(f,16);write16(f,1);write16(f,2);write32(f,rate);write32(f,rate*4);write16(f,4);write16(f,16);f.write("data",4);write32(f,uint32_t(samples.size()*4));
 for(auto s:samples){write16(f,uint16_t(int16_t(std::clamp(s.left*gain,-1.f,1.f)*32767)));write16(f,uint16_t(int16_t(std::clamp(s.right*gain,-1.f,1.f)*32767)));}if(!f)throw Xcept("WAV write failed");
}
int main(int argc,char**argv){try{
 Debug::set_callback(log_cb,nullptr);if(argc<3){std::cerr<<"render ROM scan | ROM TABLE COUNT SONG OUTWAV [seconds=240] [rate=44100]\n";return 2;}
 auto rom=Rom::LoadFromFile(argv[1]);
 if(std::string(argv[2])=="scan"){
  auto scans=MP2KScanner(rom).Scan(nullptr);for(auto&r:scans){std::cout<<"table="<<r.songTableInfo.pos<<" count="<<r.songTableInfo.count<<" vol="<<int(r.mp2kSoundMode.vol)<<" reverb="<<int(r.mp2kSoundMode.rev)<<" freq="<<int(r.mp2kSoundMode.freq)<<" dac="<<int(r.mp2kSoundMode.dacConfig)<<" players="<<r.playerTableInfo.size()<<'\n';}return 0;
 }
 if(argc<6)return 2;size_t table=std::stoull(argv[2],nullptr,0);uint16_t count=uint16_t(std::stoi(argv[3])),song=uint16_t(std::stoi(argv[4]));double maxSec=argc>6?std::stod(argv[6]):240;uint32_t rate=argc>7?std::stoi(argv[7]):44100;
 MP2KSoundMode mode;mode.vol=12;mode.rev=0;mode.freq=4;mode.maxChannels=8;mode.dacConfig=9;
 // Both supplied GameFreak ROMs use the same sound-driver mixer configuration.
 AgbplaySoundMode agb;agb.resamplerTypeNormal=ResamplerType::SINC;agb.resamplerTypeFixed=ResamplerType::SINC;
 PlayerTableInfo players(4,PlayerInfo{16,0});SongTableInfo st{table,count,0};
 MP2KContext ctx(rate,-1,rom,mode,agb,st,players);ctx.m4aSongNumStart(song);
 std::vector<sample> samples; samples.reserve(size_t(rate*std::min(90.,maxSec)));uint32_t voices=0;size_t end=0;bool capped=false;
 while(true){ctx.renderSampleCursor=samples.size();ctx.m4aSoundMain();samples.insert(samples.end(),ctx.masterAudioBuffer.begin(),ctx.masterAudioBuffer.end());
  for(auto&p:ctx.players)for(auto&t:p.tracks)voices|=uint32_t(t.activeVoiceTypes);
  std::vector<MP2KContext::LoopMark> primary;for(auto&m:ctx.renderLoops)if(m.track==0)primary.push_back(m);
  // Keep two complete cycles; the second is warmed and suitable for seamless repeat.
  if(primary.size()>=2){end=primary[1].endSample;samples.resize(end);break;}
  if(ctx.SongEnded())break;
  if(samples.size()>=size_t(maxSec*rate)){capped=true;break;}
 }
 float peak=0;double energy=0;size_t nonzero=0;for(auto&s:samples){peak=std::max({peak,std::abs(s.left),std::abs(s.right)});energy+=double(s.left)*s.left+double(s.right)*s.right;if(s.left!=0||s.right!=0)nonzero++;}
 float gain=peak>0.95f?0.95f/peak:1.f;wave(argv[5],samples,gain,rate);
 std::vector<MP2KContext::LoopMark> primary;for(auto&m:ctx.renderLoops)if(m.track==0)primary.push_back(m);
 size_t loopStart=0,loopEnd=0,introEnd=0;if(primary.size()>=2){introEnd=primary[0].endSample;loopStart=primary[0].endSample;loopEnd=primary[1].endSample;}
 std::cout<<"{\"song_id\":"<<song<<",\"sample_rate\":"<<rate<<",\"frames\":"<<samples.size()<<",\"seconds\":"<<double(samples.size())/rate<<",\"peak_before_gain\":"<<peak<<",\"gain\":"<<gain<<",\"rms\":"<<std::sqrt(energy/(std::max(size_t(1),samples.size())*2))<<",\"nonzero_frames\":"<<nonzero<<",\"voice_flags\":"<<voices<<",\"capped\":"<<(capped?"true":"false")<<",\"loop_start\":"<<loopStart<<",\"loop_end\":"<<loopEnd<<",\"sequence_intro_end\":"<<(primary.empty()?0:primary[0].startSample)<<",\"loop_marks\":"<<ctx.renderLoops.size()<<",\"track_loops\":["; for(size_t i=0;i<ctx.renderLoops.size();i++){auto&m=ctx.renderLoops[i];if(i)std::cout<<",";std::cout<<"["<<int(m.track)<<","<<m.startTick<<","<<m.endTick<<","<<m.startSample<<","<<m.endSample<<"]";} std::cout<<"]}\n";
 return capped?3:0;
 }catch(std::exception&e){std::cerr<<"RENDER FAILED: "<<e.what()<<'\n';return 1;}}
