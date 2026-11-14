# Slide recreation prompts — GraalVMs_Ahead-of-Time_Compilation_(Source).mp4

## Slide 1

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #595855, #ffffe6, #feffff.
Title: "GraalVM"
Content, top to bottom:
- GraalVM's Ahead-of-Time Compilation:
- Benefits and Challenges in Production
- 三
- JVM
- Java
- NATIVE IMAGE
- StefanWilke
- Presented by
- (JavaVirtualMachine)
- Ruwan L...
- Johan A...
- TomEvaldsson
- Jorgen S...
- Mohamad YazanBardakani
- Mattias...
- Leif Joha...
- Aleksand...
- Viktor En...
- David M...
- Carl-Fre...
- | EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 I Open | Page 1 of 15
- Axel Nau...
- Anders B...
- Tom Lars Christian Evaldsson
```

## Slide 2

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #010100, #a1a19b, #fffff3.
Title: "Table of contents"
Content, top to bottom:
- 三
- Introduction
- Explanation of Key Terms
- 1.
- Research Questions
- 2.
- Broader Interest
- 3.
- Research Method
- StefanWilke
- 4.
- 5.
- 6.
- Analysis of findings
- Results-Performance
- Results - Resource Usage
- Benchmarksuite
- 7.
- 8.
- 10. Developer Perceptions of GraalVM Integration
- 11. Value of the Work
- Ruwan L..
- Johan A...
- 12. Validity Threats and Future Work
- 9.
- Aleksand...
- Jorgen S...
- Leif Joha...
- Mattias ...
- Viktor En...
```

## Slide 3

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #3f3f3c, #ffffe7, #feffff.
Title: "Introduction"
Content, top to bottom:
- 三
- Area
- Problem
- Traditional JVMs
- JVM (Java Virtual Machine) Performance
- Optimization
- StefanWilke
- Resourceefficiency&Slowstartup&warmuptimes
- Microservices&Serverlessfunctions
- Ruwan L...
- Johan A..
- Adam Al...
- Jorgen S...
- Leif Joha...
- Mattias ...
- Viktor En...
- Axel Nau...
- David M...
- I EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 I Open | Page 3 of 15
- Anders B...
- Carl-Fre...
- Tom LarsChristian Evaldsson
```

## Slide 4

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #6a6a68, #fffffe, #feffff.
Title: "Explanation of Key Terms"
Content, top to bottom:
- =
- GraalVM
- PGO
- AOT Compilation
- JIT Compilation
- (Ahead-Of-Time)
- (Just-In-Time)
- multiple programming
- Anadvancedvirtual
- (Profile Guided Optimization)
- program is optimized based
- A technique used in AOT
- GraalVM.
- Compiling code into a
- Compiling code at
- machine that supports
- before running it.
- languages and includes
- native executable
- startup.
- Stefan Wilke
- compilation where the
- runtime,whichallowsfor
- behavior collected during a
- both Just-In-Time (JIT)
- and Ahead-of-Time
- native-image
- dynamicoptimizations
- (AOT) compilation.
- profiling run.
```

## Slide 5

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #030302, #b2b2ad, #ffffbe.
Title: "Research Questions"
Content, top to bottom:
- 三
- - RQ1: How does the performance of GraalVM's native image compare to the standard JVM regarding
- executionspeed?
- Comparing performance of JIT vs AOT
- - RQ2: How does using native image impact resource usage compared to the standard JVM?
- ComparingresourceusageofJITvsAoT
- StefanWilke
- - RQ3: How do developers and system administrators perceive the integration of GraalVM into existing
- workflowsand itsimpactonoperationalefficiency?
- Ruwan L..
- Johan A...
- Jorgen S...
- Leif Joha...
- Adam Al...
- Mattias ...
- Viktor En...
- Axel Nau...
- David M...
- | EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 | Open | Page 5 of 15
- Anders B...
- Carl-Fre...
- Tom Lars Christian Evaldsson
- +18
```

## Slide 6

```
Create a 16:9 presentation slide (single-column, mostly text).
Background colour #ffffff; accent colours #505757, #fefffa, #feffff.
Title: "Broader Interest"
Content, top to bottom:
- 三
- Sustainability
- Microservices
- Cost-Effectiveness
- StefanWilke
- Ruwan L...
- Johan A...
- Jorgen S...
- Mattias...
- Leif Joha...
- Adam Al...
- Viktor En...
- David M...
- I EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 | Open | Page 6 of 15
- Axel Nau...
- Anders B...
- Carl-Fre...
- Tom Lars Christian Evaldsson
- 19
```

## Slide 7

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #020101, #969b97, #ffffea.
Title: "Research Method"
Content, top to bottom:
- 三
- Quantitative
- Qualitative
- Performance benchmarks and resource usage
- Semi-structured interviews with industry
- professionals
- BENCH
- Stefan Wilke
- metrics
- MARKING
- Ruwan L...
- Johan A...
- Jorgen S...
- Mattias...
- Leif Joha...
- Adam Al...
- Viktor En...
- Seni-structured
- Fullystructure
- intervitw
- Unstructured
- Aauns
- David M...
- I EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 | Open | Poge 7 of 15
- Axel Nau...
- Anders B...
- Carl-Fre...
- Tom LarsChristian Evaldsson
```

## Slide 8

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #747471, #fffffe, #feffff.
Title: "Benchmark suite"
Content, top to bottom:
- =
- API endpoints:
- ●UC1: SHA256 hashing.(Zero-Prefic Hash Mining) This test uses purely
- CPU computation to stress the CPU to collect data on how performance
- is increased/decreasedwith the differentbuilds.
- ·UC2: Tert prediction. This test reads a file and, for each character, tries
- to guess the next character based on a dataset array. This test will stress
- both CPU and memory.
- StefanWilke
- ·Hotspot JIT
- The following builds were tested:
- ·Each testincluded 1o0 runson each build,taken
- · Memory usage was monitored during execution,
- 5 times to get an average of runs.
- Performance was monitored by the service
- Johan A...
- itself, to exclude outside factors.
- ·GraalVMJIT
- Native imageNoPGO
- · Compilation time and build size were recorded
- Ruwan L...
- ·Native image Full PGO
- Native imagePGO on UC1
- Adam Al...
- Jorgen S...
- for both average and peak.
- Leif Joha...
- Mattias ...
- Native image PGO onUC2
- Viktor En...
```

## Slide 9

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #72726f, #fbfffb, #fffffd.
Title: "Results - Performance"
Content, top to bottom:
- UC2performance
- ms to Process UC2- lower is better
- UC1performance
- 500
- mstoProcessUC1-lowerisbetter
- Full PGO
- 1,500
- Full PGO
- PGO onUC1
- NO PGO
- PGOonUC1
- NOPGO
- PGOon UC2
- PGO on UC2
- Hotspot JIT
- 400
- Hotspot JIT
- Stefan Wilke
- Graal JIT
- 1,000
- Graal JIT
- 300
- 500
- %diff highestvs lowest
- 200
- ~16,6%
- Graal JIT
- 179.7
- Lowest time
- ~6,5%
```

## Slide 10

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #565750, #fefffe, #fffffe.
Title: "Analysis of Findings"
Content, top to bottom:
- =
- Resource Efficiency
- Performance
- Trade-offs
- Native images can outperform JIT
- Increased build size and compilation
- native images.
- Significant memorysavingswith
- time, tons more complexity and
- in specific cases with PGO, and
- StefanWilke
- configuration.PGOincreases
- unlikeJIT,theydon'thavetowarm
- resource usage.
- up.
- Ruwan L...
- Johan A...
- Jorgen S...
- Leif Joha...
- Mattias...
- Adam Al...
- David M...
- Axel Nau...
- Nikhil Sri...
- | EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 | Open | Page 11 of 15
- Anders B...
- Carl-Fre...
- Tom Lars Christian Evaldsson
```

## Slide 11

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #706f6e, #fffffd, #feffff.
Title: "Results - Resource Usage"
Content, top to bottom:
- Memory
- Image size
- Average memory usage
- Peakmemoryusage
- Compilation time
- Memoryusage
- Image size
- Hotspot JIT
- ·104
- 0,841s
- No PGO
- 0,810
- Graal JIT
- 150
- 55,308
- 1.5
- UC1
- Full
- Stefan Wilke
- UC1 PGO
- 65,605
- UC2
- 66,942
- UC2 PGO
- 0.5
- 67,083
- Full PGO
- Johan A...
- 100
- Image size
```

## Slide 12

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #5e5b56, #fffff8, #feffff.
Title: "Developer Perceptions of GraalVM"
Content, top to bottom:
- =
- Integration
- Challenges
- General Awareness
- · Faster Startup Times
- · Developers displayed a
- · Reduced Memory Usage
- PerceivedBenefits
- ·Complex Configuration
- spectrum of familiarity with
- StefanWilke
- Learning Curve
- GraalVM,frombasicto
- advanced.
- Ruwan L...
- Johan A...
- Mattias ...
- Jorgen S...
- 。。。。
- Leif Joha...
- Adam Al...
- David M...
- o0
- Carl-Fre...
- Nikhil Sri...
- I EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 I Open | Page 12 of 15
- Axel Nau...
- Anders B...
- Tom Lars Christian Evaldsson
- 15
```

## Slide 13

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #5e5e5b, #fffffb, #feffff.
Title: "Value of the Work"
Content, top to bottom:
- 三
- NEWS
- GraalVM's AOT enhances JVM-based applications, especially microservices,
- by reducing memory usage. PGO ensures performance isn't compromised in
- key use cases but has drawbacks. Developers are concerned about added
- BREAKING
- configuration complexity.Performance is instant, so can be used in serverless
- StefanWilke
- functions.
- Significant potential for cost and resource efficiency improvements
- PracticalImplications
- inproductionenvironments.
- Ruwan L...
- Johan A...
- Jorgen S...
- Mattias ...
- Leif Joha...
- Adam Al...
- Axel Nau...
- David M...
- Nikhil Sri...
- | EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 I Open | Page 13 of 15
- Anders B...
- Carl-Fre...
- Tom LarsChristianEvaldsson
```

## Slide 14

```
Create a 16:9 presentation slide (two-column, mostly text).
Background colour #ffffff; accent colours #585856, #fffffe, #feffff.
Title: ">X>X>"
Content, top to bottom:
- Validity Threats and Future Work
- =
- ValidityThreats:
- ·Limited Adoption
- GraalVMreleasedin2019
- Stefan Wilke
- Sample Size
- Specific Configurations
- FutureWork:
- Furthercasestudiesinreal-worldapplications;explorationofmoreusecases
- for AOT compilation.
- Ruwan L...
- Johan A..
- Jorgen S...
- Leif Joha...
- Mattias...
- Adam Al...
- Axel Nau...
- David M...
- Nikhil Sri...
- I EEOVMTA Tom Lars Christian Evaldsson | 2024-05-27 I Open | Page 14 of 15
- Anders B...
- Carl-Fre...
- Tom Lars Christian Evaldsson
```

## Slide 15

```
Create a 16:9 presentation slide (single-column, mostly text).
Background colour #ffffff; accent colours #000000, #68675e, #040000.
Title: "Thank you for listening"
Content, top to bottom:
- StefanWilke
- Special thanks to
- Pär Karlsson
- RuwanLakmalSilva
- Ruwan L...
- Johan A..
- Jorgen S...
- Mattias ...
- Leif Joha...
- Adam Al...
- Axel Nau...
- David M...
- Nikhil Sri...
- Anders B...
- Carl-Fre...
- Tom Lars Christian Evaldsson
```
